"""Guard: no sys.path manipulation anywhere in tracked Python (PRD #132).

The editable install that ``uv sync`` performs is the one mechanism that
makes ``fetch``/``preprocess`` (and the scripts/ top-level modules)
importable. A ``sys.path.insert`` re-couples imports to load order and
fails silently when a file moves — this guard fails the suite instead.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# docs/archive holds historical code verbatim; this file names the pattern
# in its own source.
EXCLUDED_PREFIXES = ("docs/archive/",)
SELF = "tests/test_no_sys_path_hacks.py"

PATTERN = re.compile(r"sys\s*\.\s*path\s*\.\s*(insert|append)")


def test_no_sys_path_manipulation_in_tracked_python() -> None:
    files = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert files, "git ls-files returned nothing — guard would pass vacuously"

    offenders = [
        rel
        for rel in files
        if rel != SELF
        and not rel.startswith(EXCLUDED_PREFIXES)
        and PATTERN.search((REPO / rel).read_text(encoding="utf-8", errors="replace"))
    ]
    assert not offenders, (
        "sys.path manipulation reintroduced in: "
        + ", ".join(sorted(offenders))
        + " — imports resolve via the uv editable install (PRD #132); "
        "fix the packaging, not the path."
    )
