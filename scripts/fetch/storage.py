"""Filesystem layout + atomic write helpers.

All raw data lives under ``data/raw/<source_id>/current/``. Downloads
land first in ``data/raw/<source_id>/.partial/`` and are promoted to
``current/`` only after the source's ``validate()`` succeeds. This
guarantees ``current/`` either contains the previous-good copy or the
new-good copy — never a half-finished one.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import RAW_ROOT


def source_dir(source_id: str) -> Path:
    """Root directory for a source's data (e.g. ``data/raw/fcc_asr``)."""
    return RAW_ROOT / source_id


def current_dir(source_id: str) -> Path:
    """The 'good' directory the preprocess pipeline reads from."""
    return source_dir(source_id) / "current"


def partial_dir(source_id: str) -> Path:
    """Where a fetch-in-progress writes."""
    return source_dir(source_id) / ".partial"


def prepare_fresh_partial(source_id: str) -> Path:
    """Wipe and recreate the .partial directory. Returns its path."""
    p = partial_dir(source_id)
    if p.exists():
        shutil.rmtree(p)
    p.mkdir(parents=True, exist_ok=True)
    return p


def promote_partial(source_id: str) -> Path:
    """Atomically swap .partial → current. Old current is removed.

    Strategy: rename current → .old, rename .partial → current, then
    rmtree .old. If anything fails, we attempt to roll back so the user
    never ends up with no data at all.
    """
    src_root = source_dir(source_id)
    src_root.mkdir(parents=True, exist_ok=True)
    cur = current_dir(source_id)
    part = partial_dir(source_id)
    old = src_root / ".old"

    if not part.exists():
        raise FileNotFoundError(f"no .partial to promote for {source_id}")

    if old.exists():
        shutil.rmtree(old)

    rolled_back = False
    try:
        if cur.exists():
            cur.rename(old)
        part.rename(cur)
    except OSError:
        # Roll back: put old back if we moved it
        if old.exists() and not cur.exists():
            old.rename(cur)
            rolled_back = True
        raise
    finally:
        if not rolled_back and old.exists():
            shutil.rmtree(old, ignore_errors=True)

    return cur


def directory_bytes(path: Path) -> int:
    """Recursive byte size of a directory (0 if missing)."""
    if not path.exists():
        return 0
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def human_bytes(n: int) -> str:
    """Format bytes as a short human string (e.g. '1.2 GB', '347 MB')."""
    if n is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:,.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:,.1f} PB"
