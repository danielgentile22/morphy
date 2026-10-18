"""Litestream restore drill for the write-layer SQLite (PRD #96, Module E).

Proves the backup actually restores — the "one real risk" of the hosting
decision. Drives the *real* committed ``litestream.yml`` (env-substituted) and
the real ``litestream`` binary against a local **minio** R2 stand-in:

  1. seed a SQLite DB and replicate it to the bucket;
  2. write more rows *after* the initial snapshot (exercising WAL streaming);
  3. delete the DB + WAL + SHM (simulate volume loss);
  4. ``litestream restore`` from the replica;
  5. assert full row/content parity.

If the replica or restore path were misconfigured, the recovered DB would be
missing rows and this goes red — before we ever depend on it in prod.
"""

from __future__ import annotations

import http.client
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

_LITESTREAM = shutil.which("litestream")
_MINIO = shutil.which("minio")
_MC = shutil.which("mc")
_CONFIG = Path(__file__).resolve().parents[1] / "litestream.yml"

pytestmark = pytest.mark.skipif(
    not (_LITESTREAM and _MINIO and _MC),
    reason="litestream, minio and mc must all be installed",
)

_ROOT_USER = "minioadmin"
_ROOT_PASSWORD = "minioadmin"
_BUCKET = "morphy-litestream-drill"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_http_ok(port: int, path: str, proc: subprocess.Popen, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read() if proc.stdout else ""
            raise RuntimeError(f"minio exited early:\n{out}")
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
            conn.request("GET", path)
            if conn.getresponse().status == 200:
                conn.close()
                return
            conn.close()
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("minio did not become ready in time")


@pytest.fixture
def minio_replica(tmp_path: Path):
    """A running minio + an empty bucket; yields the env that points the real
    litestream.yml at it."""
    data_dir = tmp_path / "minio-data"
    data_dir.mkdir()
    mc_config = tmp_path / "mc-config"
    api_port = _free_port()
    console_port = _free_port()

    minio_env = {
        **os.environ,
        "MINIO_ROOT_USER": _ROOT_USER,
        "MINIO_ROOT_PASSWORD": _ROOT_PASSWORD,
    }
    proc = subprocess.Popen(
        [
            _MINIO,
            "server",
            str(data_dir),
            "--address",
            f"127.0.0.1:{api_port}",
            "--console-address",
            f"127.0.0.1:{console_port}",
        ],
        env=minio_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_http_ok(api_port, "/minio/health/live", proc)
        endpoint = f"http://127.0.0.1:{api_port}"
        _mc(mc_config, "alias", "set", "drill", endpoint, _ROOT_USER, _ROOT_PASSWORD)
        _mc(mc_config, "mb", f"drill/{_BUCKET}")

        yield {
            "LITESTREAM_BUCKET": _BUCKET,
            "LITESTREAM_PATH": "lead_state",
            "LITESTREAM_ENDPOINT": endpoint,
            "LITESTREAM_REGION": "us-east-1",
            "LITESTREAM_ACCESS_KEY_ID": _ROOT_USER,
            "LITESTREAM_SECRET_ACCESS_KEY": _ROOT_PASSWORD,
        }
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _mc(config_dir: Path, *args: str) -> None:
    subprocess.run(
        [_MC, "--config-dir", str(config_dir), "--quiet", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _seed_db(path: Path, names: list[str]) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute("PRAGMA journal_mode=WAL")  # litestream replicates the WAL
        con.execute("CREATE TABLE leads (id INTEGER PRIMARY KEY, name TEXT)")
        con.executemany("INSERT INTO leads (name) VALUES (?)", [(n,) for n in names])
        con.commit()
    finally:
        con.close()


def _read_names(path: Path) -> list[str]:
    con = sqlite3.connect(path)
    try:
        return [row[0] for row in con.execute("SELECT name FROM leads ORDER BY id")]
    finally:
        con.close()


def _litestream(
    env_overrides: dict[str, str], subcommand: str, *args: str
) -> subprocess.CompletedProcess:
    # -config must precede any positional (Go's flag parser stops at the first
    # non-flag arg), so it goes right after the subcommand.
    return subprocess.run(
        [_LITESTREAM, subcommand, "-config", str(_CONFIG), *args],
        env={**os.environ, **env_overrides},
        capture_output=True,
        text=True,
    )


def test_litestream_config_lists_the_configured_db(minio_replica: dict[str, str]) -> None:
    # Cheap guard: the real config parses and its ${VAR}s expand to our DB path.
    db = "/tmp/morphy-drill.sqlite3"
    proc = _litestream({**minio_replica, "LITESTREAM_DB_PATH": db}, "databases")
    assert proc.returncode == 0, proc.stderr
    assert db in proc.stdout


def test_restore_recovers_all_rows_after_volume_loss(
    minio_replica: dict[str, str], tmp_path: Path
) -> None:
    db = tmp_path / "lead_state.sqlite3"
    _seed_db(db, ["alpha", "bravo"])

    env = {**minio_replica, "LITESTREAM_DB_PATH": str(db)}

    # A helper that writes two MORE rows after litestream has snapshotted, so the
    # restore must combine the snapshot with streamed WAL frames. The sleep lets
    # a replication interval elapse before the child exits (litestream final-syncs
    # on exit too — belt and suspenders).
    inserter = tmp_path / "post_snapshot_insert.py"
    inserter.write_text(
        "import os, sqlite3, time\n"
        'con = sqlite3.connect(os.environ["DRILL_DB"])\n'
        "con.execute(\"INSERT INTO leads (name) VALUES ('charlie'), ('delta')\")\n"
        "con.commit(); con.close()\n"
        "time.sleep(2)\n"
    )
    replicate = _litestream(
        {**env, "DRILL_DB": str(db)},
        "replicate",
        "-exec",
        f"{sys.executable} {inserter}",
    )
    assert replicate.returncode == 0, replicate.stderr

    # Simulate volume loss: the DB and its sidecar WAL/SHM are gone.
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db) + suffix)
        if p.exists():
            p.unlink()
    assert not db.exists()

    restored = tmp_path / "restored.sqlite3"
    restore = _litestream(env, "restore", "-o", str(restored), str(db))
    assert restore.returncode == 0, restore.stderr

    assert _read_names(restored) == ["alpha", "bravo", "charlie", "delta"]
