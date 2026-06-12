"""The deterministic OpenAPI export (PRD #133).

The export script is the root of the generated-types chain
(``backend/openapi.json`` → ``app/src/lib/api-types.ts``), so what matters
here is the *contract surface*: the export runs without a server and is
byte-stable across runs (CI's drift gate diffs bytes, so any flap breaks
it), the committed schema is current, and the schema fully declares the
fields the frontend's generated types are built from — the
silently-dropped-undeclared-field gotcha made visible.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMMITTED = REPO / "backend" / "openapi.json"


def _run_export(out: Path) -> None:
    """Run the export the way CI does: a fresh process, no server, repo-root cwd."""
    subprocess.run(
        [sys.executable, "-m", "scripts.export_openapi", str(out)],
        cwd=REPO,
        check=True,
        capture_output=True,
    )


def test_export_runs_without_a_server_and_is_byte_stable(tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    _run_export(a)
    _run_export(b)
    assert a.read_bytes() == b.read_bytes(), "two exports differ — the drift gate would flap"
    doc = json.loads(a.read_text(encoding="utf-8"))
    assert doc["openapi"].startswith("3."), "not an OpenAPI document"


def test_committed_schema_is_current() -> None:
    """``backend/openapi.json`` matches a fresh in-process export — the local
    twin of CI's git-diff drift gate. Red here means: regenerate with
    ``uv run python -m scripts.export_openapi`` (then ``npm run generate:api``
    in app/) and commit both artifacts."""
    import tempfile

    from scripts.export_openapi import export_schema

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "openapi.json"
        export_schema(out)
        assert out.read_bytes() == COMMITTED.read_bytes(), (
            "backend/openapi.json is stale — regenerate it "
            "(uv run python -m scripts.export_openapi) and the frontend types "
            "(cd app && npm run generate:api), then commit both."
        )


def test_schema_declares_the_lead_page_contract() -> None:
    """Completeness for the highest-traffic endpoint: the Lead page reads
    LeadDetail → OwnerSummary/Holding/Structure. Every field the frontend's
    generated types consume must be *declared* here — an undeclared response
    field is silently dropped by FastAPI's response_model, which is exactly
    the bug class this export exists to surface."""
    doc = json.loads(COMMITTED.read_text(encoding="utf-8"))

    lead_get = doc["paths"]["/api/leads/{display_cluster_id}"]["get"]
    ref = lead_get["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ref == "#/components/schemas/LeadDetail"

    schemas = doc["components"]["schemas"]
    owner_props = set(schemas["OwnerSummary"]["properties"])
    assert owner_props >= {
        # core summary
        "display_cluster_id",
        "owner_name",
        "owner_kind",
        "states",
        "score",
        "status",
        # v3 filter rollups (#52)
        "counties",
        "structure_count",
        "structure_types",
        "active_tower_count",
        "tallest_tower_height_m",
        # pursuit trigger (#109)
        "trigger_asr",
    }
    # The Slice-A regression this gate exists for: carriers must stay declared
    # on Structure (undeclared = dropped from responses = missing type).
    assert "carriers" in schemas["Structure"]["properties"]
    assert "structures" in schemas["Holding"]["properties"]
