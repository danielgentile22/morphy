"""M8 · Freshness exporter — snapshot the puller manifest into ``freshness.json``.

The data feed behind the Data Catalog's **"What needs updating"** view. It
projects the live puller manifest (``data/manifest.json``, schema v2) through a
curated **source → audit mapping** (M10) into a small ``freshness.json`` artifact
written into the audit artifacts dir (``docs/research/data-audit/``). That dir is
baked into the production image (``Dockerfile`` → ``/srv/audit-data``) and served
at ``/audit/data/freshness.json`` exactly like ``index.json`` — so the catalog
fetches it live, behind the same session gate.

It runs at **deploy time, before the image build**, because ``data/`` is
git-ignored and absent from the build context (so ``freshness.json`` is itself
git-ignored — a generated deploy artifact, never committed). See ``deploy.sh``.

Honest-by-construction: the "last pulled" truth lives on whatever machine runs
the puller, so this snapshot is *last-pulled-as-of-deploy*. The client freshness
model (M9) advances the due/overdue countdown day-by-day from the baked snapshot,
mirroring ``fetch.manifest.SourceEntry.freshness()`` — which is exactly the
projection this exporter reuses, so the two never drift.

Pure projection: ``build_freshness(manifest_dict, now=…)`` takes a manifest dict
and a fixed ``now`` and returns the doc — no network, no real data dir. A missing
or unreadable manifest degrades gracefully to a valid doc with unknown pull state.

────────────────────────────────────────────────────────────────────────────────
``freshness.json`` contract (the shape the client M9/M11 reads)
────────────────────────────────────────────────────────────────────────────────
    {
      "schema_version": 1,
      "generated_at": "<ISO8601>",          # when this exporter ran (deploy time)
      "manifest": {
        "present": true,                     # was data/manifest.json readable?
        "last_full_check": "<ISO8601>|null"  # manifest's own last sweep time
      },
      "note": "<plain-English honesty caveat>",
      "sources": [                           # one entry per refreshable audit source
        {
          "id": "T-01",                      # audit card id — the stable join key
          "title": "fcc-asr",               # human label (the dossier slug)
          "kind": "fetched" | "derived",
          "manifest_source_ids": ["fcc_asr"],# puller source(s) behind this entry
          "last_pulled": "<ISO8601>|null",   # oldest input's fetch time, or null
          "cadence_days": <int>|null,        # tightest declared cadence, or null
          "next_check": "<ISO8601>|null",    # earliest recommended re-check, or null
          "status": "fresh"|"due_soon"|"stale"|"unknown"|"rebuilt",
          "rebuilt_not_fetched": false       # true ⇔ derived (no pull date expected)
        },
        ...
      ]
    }

Per-entry rules:
- ``kind == "fetched"``: projects ``last_pulled`` / ``cadence_days`` / ``next_check``
  / ``status`` from its manifest source(s). ``status`` is the freshness vocab
  (``fresh`` / ``due_soon`` / ``stale`` / ``unknown``) computed at export time.
- A fetched source with **no declared cadence** (or never pulled) yields
  ``status == "unknown"`` with ``cadence_days``/``next_check`` ``null`` — no
  fabricated due-date.
- ``kind == "derived"``: data the pipeline *rebuilds*, never pulls. Always
  ``status == "rebuilt"`` / ``rebuilt_not_fetched == true`` with null pull fields.
- **Composite** audit sources (several manifest inputs) report the *bottleneck*:
  oldest ``last_pulled``, earliest ``next_check``, tightest ``cadence_days``, and
  the **worst** input status (``stale`` > ``due_soon`` > ``fresh`` > ``unknown``).

A missing ``freshness.json`` downstream means "not yet generated" — the catalog
degrades to a quiet placeholder, never a broken tab.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from fetch import MANIFEST_PATH, PROJECT_ROOT
from fetch.manifest import (
    FRESHNESS_DUE_SOON,
    FRESHNESS_FRESH,
    FRESHNESS_STALE,
    FRESHNESS_UNKNOWN,
    SourceEntry,
)

SCHEMA_VERSION = 1

# Default output: the audit artifacts dir, baked into the image + served at
# /audit/data/freshness.json (computed from the repo root the puller agrees on).
DEFAULT_OUT = PROJECT_ROOT / "docs" / "research" / "data-audit" / "freshness.json"

# ── audit-source kinds ──────────────────────────────────────────────────────
FETCHED = "fetched"  # backed by puller manifest source(s) — has a real pull date
DERIVED = "derived"  # rebuilt by the pipeline, never pulled

# Status assigned to derived sources (distinct from the fetched freshness vocab).
STATUS_REBUILT = "rebuilt"

# How "needy" each input status is, for rolling a composite up to its worst input.
_SEVERITY = {
    FRESHNESS_STALE: 3,
    FRESHNESS_DUE_SOON: 2,
    FRESHNESS_FRESH: 1,
    FRESHNESS_UNKNOWN: 0,
}


@dataclass(frozen=True)
class AuditSource:
    """One refreshable audit source = one catalog dossier (M10 mapping value)."""

    title: str
    kind: str  # FETCHED | DERIVED
    source_ids: tuple[str, ...] = field(default_factory=tuple)


# ── M10 · Source → audit mapping (curated) ──────────────────────────────────
# Keyed by audit **card id** (the stable join key in index.json; a card's signals
# carry ``card``). Each refreshable audit source is either FETCHED (projects
# pull state from one or more puller manifest ``source_id``s) or DERIVED (rebuilt
# by the preprocess pipeline — "rebuilt, not fetched", no pull date).
#
# The ``source_id`` strings are puller registry ids (scripts/fetch/registry.py).
# test_export_freshness asserts they all still resolve, so a rename trips CI.
AUDIT_SOURCE_MAP: dict[str, AuditSource] = {
    # ── Fetched — towers ────────────────────────────────────────────────────
    "T-01": AuditSource("fcc-asr", FETCHED, ("fcc_asr",)),
    "T-02": AuditSource("faa-dof", FETCHED, ("faa_oeaaa",)),
    # Carrier identity is derived, but its freshness is gated by the ULS pull it
    # reads — so it tracks the ULS bulk files (re-pull ULS to refresh carriers).
    "T-03": AuditSource("carrier-identification", FETCHED, ("fcc_uls_cellular", "fcc_uls_market")),
    # ── Fetched — parcels (one state source each) ───────────────────────────
    "T-04": AuditSource("parcels-FL", FETCHED, ("fdor_nal",)),
    "T-05": AuditSource("parcels-AR", FETCHED, ("ar_parcels",)),
    "T-06": AuditSource("parcels-MT", FETCHED, ("mt_cadastral_parcels",)),
    "T-07": AuditSource("parcels-WV", FETCHED, ("wv_parcels",)),
    # ── Fetched — distress overlays (composite of the four overlay pulls) ────
    "T-10": AuditSource(
        "distress-overlays",
        FETCHED,
        ("hud_oz", "hud_qct", "arc_distressed", "usda_persistent_poverty"),
    ),
    # ── Fetched — exploratory feeds (captured; cadence may be unknown) ───────
    "T-13": AuditSource("billboards-FL", FETCHED, ("fdot_billboards",)),
    "T-20": AuditSource("solar-feeds", FETCHED, ("uspvdb", "eia_860", "eia_860m")),
    # ── Derived — rebuilt by the pipeline, never pulled ─────────────────────
    "T-08": AuditSource("owner-clustering", DERIVED),
    "T-09": AuditSource("owner-type-classification", DERIVED),
    "T-11": AuditSource("interestingness-score", DERIVED),
    "T-12": AuditSource("parcel-tower-join", DERIVED),
}

# Audit cards deliberately *not* in the freshness view — they audit the *process*
# or other sources, not a refreshable data feed of their own:
#   T-00 enumeration/completeness · T-21 lead-enrichment-feeds (discovery, no
#   signals) · T-22 raw-column-sweep (a sweep across existing sources) ·
#   T-30 external-discovery (data we don't have) · T-90 reconciliation ·
#   T-91 adversarial-verification.
# test_export_freshness asserts every index.json card is mapped OR listed here,
# so a *new* dossier can never be silently dropped from the view.
EXCLUDED_CARDS: frozenset[str] = frozenset({"T-00", "T-21", "T-22", "T-30", "T-90", "T-91"})


# ── projection ──────────────────────────────────────────────────────────────
def _parse(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _entry_from_manifest(manifest: dict, source_id: str) -> SourceEntry:
    """Reconstruct a SourceEntry from a manifest dict (same key-filtering as
    ``Manifest.load``), so a never-seen source becomes a default (uninstalled)
    entry rather than a crash."""
    raw = manifest.get("sources", {}).get(source_id, {})
    valid = SourceEntry.__dataclass_fields__.keys()
    return SourceEntry(**{k: v for k, v in raw.items() if k in valid})


def _project_fetched(manifest: dict, source_ids: tuple[str, ...], now: datetime) -> dict:
    """Roll one or more manifest inputs up to a single audit-source projection,
    reporting the bottleneck input (oldest pull / earliest due / tightest cadence
    / worst status). Reuses SourceEntry.freshness() so thresholds match the
    puller exactly."""
    pulls: list[tuple[datetime, str]] = []
    next_checks: list[tuple[datetime, str]] = []
    cadences: list[int] = []
    statuses: list[str] = []
    for sid in source_ids:
        e = _entry_from_manifest(manifest, sid)
        statuses.append(e.freshness(now))
        p = _parse(e.fetched_at)
        if p is not None:
            pulls.append((p, e.fetched_at))  # type: ignore[arg-type]
        nra = _parse(e.next_recommended_check_at)
        if nra is not None:
            cadences.append(e.update_cadence_days)  # type: ignore[arg-type]
            next_checks.append((nra, e.next_recommended_check_at))  # type: ignore[arg-type]
        elif e.update_cadence_days is not None:
            cadences.append(e.update_cadence_days)
    return {
        "last_pulled": min(pulls, key=lambda x: x[0])[1] if pulls else None,
        "next_check": min(next_checks, key=lambda x: x[0])[1] if next_checks else None,
        "cadence_days": min(cadences) if cadences else None,
        "status": (max(statuses, key=lambda s: _SEVERITY[s]) if statuses else FRESHNESS_UNKNOWN),
    }


def build_freshness(
    manifest: dict,
    *,
    mapping: dict[str, AuditSource] = AUDIT_SOURCE_MAP,
    now: datetime,
    manifest_present: bool = True,
) -> dict:
    """Pure projection: manifest dict → freshness doc. See the module docstring
    for the emitted shape. Deterministic given ``(manifest, mapping, now)``."""
    sources: list[dict] = []
    for card_id, src in mapping.items():
        if src.kind == DERIVED:
            sources.append(
                {
                    "id": card_id,
                    "title": src.title,
                    "kind": DERIVED,
                    "manifest_source_ids": [],
                    "last_pulled": None,
                    "cadence_days": None,
                    "next_check": None,
                    "status": STATUS_REBUILT,
                    "rebuilt_not_fetched": True,
                }
            )
            continue
        proj = _project_fetched(manifest, src.source_ids, now)
        sources.append(
            {
                "id": card_id,
                "title": src.title,
                "kind": FETCHED,
                "manifest_source_ids": list(src.source_ids),
                "last_pulled": proj["last_pulled"],
                "cadence_days": proj["cadence_days"],
                "next_check": proj["next_check"],
                "status": proj["status"],
                "rebuilt_not_fetched": False,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(timespec="seconds"),
        "manifest": {
            "present": manifest_present,
            "last_full_check": manifest.get("last_full_check"),
        },
        "note": (
            "Last-pulled is a snapshot captured at deploy time; the due/overdue "
            "countdown advances day-by-day from it. Derived data is rebuilt by "
            "the pipeline, not pulled."
        ),
        "sources": sources,
    }


def _write_json(path: Path, doc: dict) -> None:
    """Atomic write: temp file in the same dir, then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".freshness.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(doc, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_manifest(path: Path) -> tuple[dict, bool]:
    """Read a manifest dict; degrade to ``({}, False)`` if absent/corrupt so the
    exporter still emits a valid (unknown-pull-state) doc."""
    if not path.exists():
        print(f"warning: {path} not found — emitting freshness with unknown pull state")
        return {}, False
    try:
        return json.loads(path.read_text()), True
    except (json.JSONDecodeError, OSError) as exc:
        print(f"warning: could not read {path} ({exc}) — emitting unknown pull state")
        return {}, False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Snapshot the puller manifest into freshness.json for the Data Catalog."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST_PATH,
        help="path to data/manifest.json (default: the puller's manifest)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="output freshness.json path (default: the audit artifacts dir)",
    )
    args = parser.parse_args(argv)

    manifest, present = _load_manifest(args.manifest)
    doc = build_freshness(manifest, now=datetime.now(UTC), manifest_present=present)
    _write_json(args.out, doc)
    print(f"wrote {args.out} — {len(doc['sources'])} sources (manifest_present={present})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
