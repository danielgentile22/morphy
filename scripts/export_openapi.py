"""Export the backend's OpenAPI schema deterministically (PRD #133).

Imports the FastAPI app object and dumps ``app.openapi()`` as JSON with
sorted keys — no server boot, no database connection. The committed output
(``backend/openapi.json``) is the source of truth for the frontend's
generated types module (``app/src/lib/api-types.ts``); CI regenerates both
and fails on drift, so a response-model change that isn't regenerated +
committed turns the gate red instead of surfacing at runtime.

Run from the repo root (the namespace import needs the root on sys.path,
which ``-m`` provides via the working directory):

    uv run python -m scripts.export_openapi              # backend/openapi.json
    uv run python -m scripts.export_openapi /tmp/o.json  # explicit output path
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "backend" / "openapi.json"


def export_schema(out_path: Path) -> None:
    """Write the app's OpenAPI document to ``out_path``, sorted + newline-terminated."""
    # The schema comes from code alone — point the owners index at a missing
    # file before the app module loads so the import never reads the real
    # ~40 MB index (a missing file is served as an empty index by design).
    os.environ.setdefault("OWNERS_INDEX_PATH", str(REPO_ROOT / "data" / "_absent_index.json"))
    from backend.app.main import app

    doc = app.openapi()
    out_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    out = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_OUT
    export_schema(out)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
