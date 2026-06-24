"""Tests for the M8 freshness exporter (``manifest.json`` → ``freshness.json``).

Pure projection — no network, no real data dir. A fixture manifest dict goes in;
the projected freshness doc comes out. ``now`` is pinned so the freshness
thresholds (which mirror ``fetch.manifest.SourceEntry.freshness`` /
``DUE_SOON_FRACTION``) land on stable assertions.

Prior art: the preprocess fixture-projection tests + ``test_preprocess_manifest``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from export_freshness import (
    AUDIT_SOURCE_MAP,
    DERIVED,
    EXCLUDED_CARDS,
    FETCHED,
    STATUS_REBUILT,
    AuditSource,
    build_freshness,
    main,
)
from fetch.manifest import (
    FRESHNESS_DUE_SOON,
    FRESHNESS_FRESH,
    FRESHNESS_STALE,
    FRESHNESS_UNKNOWN,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_JSON = REPO_ROOT / "docs" / "research" / "data-audit" / "index.json"

NOW = datetime(2026, 6, 20, tzinfo=UTC)


# ── fixture builders ─────────────────────────────────────────────────────────
def _src(days_ago: int, cadence: int | None, status: str = "ok", anchor: datetime = NOW) -> dict:
    """A fetched manifest entry pulled ``days_ago`` days before ``anchor`` (the
    pinned NOW by default), with the given cadence (``None`` = no declared
    cadence). ``next_recommended_check_at`` is derived from the fetch + cadence,
    exactly as the puller writes it. The CLI test overrides ``anchor`` with the
    real wall-clock, since ``main()`` computes freshness against real ``now``."""
    fetched = anchor - timedelta(days=days_ago)
    entry: dict = {
        "local_version": "v1",
        "remote_version": "v1",
        "status": status,
        "fetched_at": fetched.isoformat(timespec="seconds"),
        "update_cadence_days": cadence,
    }
    if cadence is not None:
        entry["next_recommended_check_at"] = (fetched + timedelta(days=cadence)).isoformat(
            timespec="seconds"
        )
    return entry


def _manifest(sources: dict) -> dict:
    return {
        "schema_version": 2,
        "last_full_check": "2026-06-19T00:00:00+00:00",
        "sources": sources,
    }


def _by_id(doc: dict) -> dict[str, dict]:
    return {s["id"]: s for s in doc["sources"]}


def _build(sources: dict, **kw) -> dict:
    return build_freshness(_manifest(sources), now=NOW, **kw)


# ── top-level shape ──────────────────────────────────────────────────────────
def test_top_level_shape_and_required_keys():
    doc = _build({})
    assert doc["schema_version"] == 1
    assert doc["generated_at"] == NOW.isoformat(timespec="seconds")
    assert doc["manifest"]["present"] is True
    assert doc["manifest"]["last_full_check"] == "2026-06-19T00:00:00+00:00"
    assert isinstance(doc["note"], str) and doc["note"]
    assert isinstance(doc["sources"], list) and doc["sources"]
    required = {
        "id",
        "title",
        "kind",
        "manifest_source_ids",
        "last_pulled",
        "cadence_days",
        "next_check",
        "status",
        "rebuilt_not_fetched",
    }
    for s in doc["sources"]:
        assert required <= set(s), f"{s['id']} missing keys"
        assert s["kind"] in (FETCHED, DERIVED)


# ── acceptance: fetched entry carries pull date + cadence + next-check + status ─
def test_fetched_fresh_source_carries_all_fields():
    doc = _build({"fcc_asr": _src(days_ago=1, cadence=7)})
    t01 = _by_id(doc)["T-01"]  # T-01 fcc-asr → [fcc_asr]
    assert t01["kind"] == FETCHED
    assert t01["manifest_source_ids"] == ["fcc_asr"]
    assert t01["last_pulled"] is not None
    assert t01["cadence_days"] == 7
    assert t01["next_check"] is not None
    assert t01["status"] == FRESHNESS_FRESH
    assert t01["rebuilt_not_fetched"] is False


def test_fetched_status_transitions_match_manifest_thresholds():
    # fresh: just pulled · due_soon: past 50% of window · stale: past next-check
    assert _by_id(_build({"fcc_asr": _src(1, 7)}))["T-01"]["status"] == FRESHNESS_FRESH
    assert _by_id(_build({"fcc_asr": _src(5, 7)}))["T-01"]["status"] == FRESHNESS_DUE_SOON
    assert _by_id(_build({"fcc_asr": _src(10, 7)}))["T-01"]["status"] == FRESHNESS_STALE


# ── acceptance: no declared cadence ⇒ unknown, no fabricated due-date ─────────
def test_no_cadence_yields_unknown_with_no_due_date():
    doc = _build({"fcc_asr": _src(days_ago=400, cadence=None)})
    t01 = _by_id(doc)["T-01"]
    assert t01["status"] == FRESHNESS_UNKNOWN
    assert t01["cadence_days"] is None
    assert t01["next_check"] is None
    # last_pulled is still honest — we *did* pull it, we just can't judge staleness
    assert t01["last_pulled"] is not None


def test_source_absent_from_manifest_is_never_pulled():
    doc = _build({})  # no fcc_asr entry at all
    t01 = _by_id(doc)["T-01"]
    assert t01["status"] == FRESHNESS_UNKNOWN
    assert t01["last_pulled"] is None
    assert t01["cadence_days"] is None
    assert t01["next_check"] is None


# ── acceptance: derived sources flagged "rebuilt, not fetched" ───────────────
def test_derived_sources_are_rebuilt_not_fetched():
    doc = _by_id(_build({}))
    for card_id in ("T-08", "T-11", "T-12"):  # clustering, interestingness, join
        d = doc[card_id]
        assert d["kind"] == DERIVED
        assert d["rebuilt_not_fetched"] is True
        assert d["status"] == STATUS_REBUILT
        assert d["last_pulled"] is None
        assert d["cadence_days"] is None
        assert d["next_check"] is None
        assert d["manifest_source_ids"] == []


# ── composite audit source rolls up to the bottleneck input ──────────────────
def test_composite_reports_worst_input_status():
    # T-10 distress-overlays = [hud_oz, hud_qct, arc_distressed, usda_persistent_poverty]
    manifest = {
        "hud_oz": _src(2, None),  # static reference data — unknown
        "hud_qct": _src(10, 7),  # stale (past next-check)
        "arc_distressed": _src(1, 365),  # fresh
        "usda_persistent_poverty": _src(400, None),  # unknown
    }
    t10 = _by_id(_build(manifest))["T-10"]
    assert t10["status"] == FRESHNESS_STALE  # the one stale input drives it
    assert t10["cadence_days"] == 7  # tightest declared cadence among inputs
    # oldest pull (usda, 400d ago) is the reported last_pulled
    assert t10["last_pulled"] == (NOW - timedelta(days=400)).isoformat(timespec="seconds")


def test_composite_all_fresh_is_fresh():
    manifest = {
        "uspvdb": _src(1, 90),
        "eia_860": _src(2, 365),
        "eia_860m": _src(1, 30),
    }
    assert _by_id(_build(manifest))["T-20"]["status"] == FRESHNESS_FRESH


# ── degradation + determinism ────────────────────────────────────────────────
def test_missing_manifest_degrades_to_valid_unknown_doc():
    doc = build_freshness({}, now=NOW, manifest_present=False)
    assert doc["manifest"]["present"] is False
    by_id = _by_id(doc)
    # every fetched source is unknown-with-no-pull; every derived is still rebuilt
    for s in doc["sources"]:
        if s["kind"] == FETCHED:
            assert s["status"] == FRESHNESS_UNKNOWN
            assert s["last_pulled"] is None
        else:
            assert s["status"] == STATUS_REBUILT
    assert by_id["T-08"]["rebuilt_not_fetched"] is True


def test_projection_is_deterministic():
    manifest = {"fcc_asr": _src(5, 7), "faa_oeaaa": _src(10, 1)}
    assert _build(manifest) == _build(manifest)


# ── CLI writes the artifact ──────────────────────────────────────────────────
def test_cli_writes_freshness_json(tmp_path: Path):
    # main() computes freshness against the real wall-clock (not the pinned NOW),
    # so anchor the fixture to real now — otherwise "1 day ago" drifts past the
    # cadence window and the status ages fresh → due_soon → stale over time.
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(_manifest({"fcc_asr": _src(1, 7, anchor=datetime.now(UTC))}))
    )
    out = tmp_path / "freshness.json"
    rc = main(["--manifest", str(manifest_path), "--out", str(out)])
    assert rc == 0
    doc = json.loads(out.read_text())
    assert _by_id(doc)["T-01"]["status"] == FRESHNESS_FRESH
    assert doc["manifest"]["present"] is True


def test_cli_missing_manifest_still_writes(tmp_path: Path):
    out = tmp_path / "freshness.json"
    rc = main(["--manifest", str(tmp_path / "absent.json"), "--out", str(out)])
    assert rc == 0
    assert json.loads(out.read_text())["manifest"]["present"] is False


# ── M10 mapping integrity (guards against silent drift) ──────────────────────
def test_every_index_card_is_mapped_or_explicitly_excluded():
    """No dossier may be silently dropped from the freshness view — every card in
    the live index.json must be either mapped (M10) or in EXCLUDED_CARDS."""
    cards = {c["id"] for c in json.loads(INDEX_JSON.read_text())["cards"]}
    accounted = set(AUDIT_SOURCE_MAP) | EXCLUDED_CARDS
    unaccounted = cards - accounted
    assert not unaccounted, (
        f"index.json cards not mapped nor excluded: {sorted(unaccounted)} — "
        "add them to AUDIT_SOURCE_MAP or EXCLUDED_CARDS in export_freshness.py"
    )
    # and the map/exclusions don't reference cards that no longer exist
    assert accounted <= cards, f"mapping references unknown cards: {sorted(accounted - cards)}"


def test_mapping_and_exclusions_are_disjoint():
    assert not (set(AUDIT_SOURCE_MAP) & EXCLUDED_CARDS)


def test_fetched_source_ids_exist_in_the_registry():
    """Every manifest source_id in the M10 mapping must still resolve in the
    puller registry — a source rename trips this instead of shipping dead ids."""
    from fetch.registry import get_source

    referenced = {sid for src in AUDIT_SOURCE_MAP.values() for sid in src.source_ids}
    missing = []
    for sid in sorted(referenced):
        try:
            get_source(sid)
        except KeyError:
            missing.append(sid)
    assert not missing, f"M10 references unknown puller source ids: {missing}"


def test_derived_sources_declare_no_source_ids():
    for card_id, src in AUDIT_SOURCE_MAP.items():
        if src.kind == DERIVED:
            assert src.source_ids == (), f"{card_id} is derived but lists source_ids"
        else:
            assert src.source_ids, f"{card_id} is fetched but lists no source_ids"


def test_auditsource_is_constructible_without_source_ids():
    s = AuditSource("x", DERIVED)
    assert s.source_ids == ()
