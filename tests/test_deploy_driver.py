"""Deploy driver (#239): sequencing + streaming, against a stub deploy script.

The invariant under test is operational: the restart runs strictly after
the sync leg exits (never mid-sync), only when the owners index changed,
and a failed sync stops the run before restart/smoke ever start.
"""

from __future__ import annotations

import stat
from pathlib import Path

from data_tui.deploy import apply_steps, dry_run, owners_changed, run_apply

OWNERS = {"schema_version": 5, "count": 500, "generated_at": "2026-07-01T00:00:00+00:00"}


def _stub(tmp_path: Path, name: str, fail_on: str = "") -> tuple[Path, Path]:
    """Shell stub that logs its args and can fail on one subcommand."""
    log = tmp_path / f"{name}.log"
    script = tmp_path / name
    script.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        'echo "out: $@"\n'
        f'[ -n "{fail_on}" ] && [ "$1" = "{fail_on}" ] && exit 1\n'
        "exit 0\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script, log


def _invocations(log: Path) -> list[str]:
    return log.read_text().splitlines() if log.exists() else []


def test_apply_steps_order_sync_restart_smoke(tmp_path):
    steps = apply_steps("deploy.sh", restart_needed=True, restart_argv=("fly", "restart"))
    assert [name for name, _ in steps] == ["sync", "restart", "smoke"]
    assert steps[0][1] == ("deploy.sh", "data", "--apply")
    assert steps[-1][1] == ("deploy.sh", "smoke")


def test_apply_steps_skip_restart_when_owners_unchanged(tmp_path):
    steps = apply_steps("deploy.sh", restart_needed=False)
    assert [name for name, _ in steps] == ["sync", "smoke"]


def test_run_apply_streams_and_orders_invocations(tmp_path):
    script, log = _stub(tmp_path, "deploy.sh")
    restart, rlog = _stub(tmp_path, "fly")
    lines: list[tuple[str, str]] = []
    results = run_apply(
        apply_steps(script, restart_needed=True, restart_argv=(str(restart), "restart")),
        lambda s, line: lines.append((s, line)),
    )
    assert [r.step for r in results] == ["sync", "restart", "smoke"]
    assert all(r.ok for r in results)
    # The deploy script saw sync strictly before smoke; restart ran between.
    assert _invocations(log) == ["data --apply", "smoke"]
    assert _invocations(rlog) == ["restart"]
    assert ("sync", "out: data --apply") in lines
    assert ("smoke", "out: smoke") in lines


def test_failed_sync_stops_before_restart_and_smoke(tmp_path):
    script, log = _stub(tmp_path, "deploy.sh", fail_on="data")
    restart, rlog = _stub(tmp_path, "fly")
    results = run_apply(
        apply_steps(script, restart_needed=True, restart_argv=(str(restart), "restart")),
        lambda s, line: None,
    )
    assert [r.step for r in results] == ["sync"]
    assert not results[0].ok
    assert _invocations(log) == ["data --apply"]  # no smoke leg
    assert _invocations(rlog) == []  # restart never ran mid-/post-failure


def test_failed_restart_stops_before_smoke(tmp_path):
    script, log = _stub(tmp_path, "deploy.sh")
    restart, _ = _stub(tmp_path, "fly", fail_on="restart")
    results = run_apply(
        apply_steps(script, restart_needed=True, restart_argv=(str(restart), "restart")),
        lambda s, line: None,
    )
    assert [r.step for r in results] == ["sync", "restart"]
    assert _invocations(log) == ["data --apply"]


def test_dry_run_never_passes_apply(tmp_path):
    script, log = _stub(tmp_path, "deploy.sh")
    lines: list[tuple[str, str]] = []
    result = dry_run(script, lambda s, line: lines.append((s, line)))
    assert result.ok
    assert _invocations(log) == ["data"]
    assert ("dry-run", "out: data") in lines


def test_owners_changed():
    assert owners_changed(OWNERS, None)  # no receipt → always restart
    assert not owners_changed(OWNERS, {"owners": dict(OWNERS)})
    assert owners_changed(OWNERS, {"owners": {**OWNERS, "count": 400}})
