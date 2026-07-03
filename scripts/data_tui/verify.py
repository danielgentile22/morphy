"""Composite verify (#239) — the pure decision brain of the deploy gate.

Diffs the freshly composed data against the last **deploy receipt** (what
actually shipped last time — verify never talks to prod): per-state
parcel/tower counts with a drop threshold, owners-index schema version +
row count, and the file inventory the sync contract
(``sync_composite.iter_sync_files``) would ship. Any failed check blocks
deploy pending an explicit, logged override. With no receipt yet (first
run) there is nothing to diff — verify reports and never blocks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fetch import PROJECT_ROOT
from sync_composite import iter_sync_files

COMPOSITE_ROOT = PROJECT_ROOT / "data" / "processed" / "composite"
RECEIPT_PATH = PROJECT_ROOT / "data" / "deploy_receipt.json"
DROP_THRESHOLD = 0.10  # a count this far below the receipt's fails the check
_COUNT_KINDS = ("parcel", "tower")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class VerifyReport:
    checks: tuple[Check, ...]
    baseline_at: str | None  # receipt's deployed_at; None = first run
    fresh: dict | None  # snapshot of the composite under verification

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def blocks_deploy(self) -> bool:
        # Only receipt comparisons can fail; a first run has none to fail.
        return not self.passed


def snapshot(composite_dir: Path) -> dict:
    """What a deploy would ship: per-state parcel/tower counts, owners-index
    meta, and the served-file inventory under the sync contract."""
    index = json.loads((composite_dir / "index.json").read_text())
    owners = json.loads((composite_dir / "owners_index.json").read_text())
    return {
        "state_counts": {
            s["fips"]: {k: s["counts"].get(k, 0) for k in _COUNT_KINDS} for s in index["states"]
        },
        "owners": {
            "schema_version": owners.get("schema_version"),
            "count": owners.get("count"),
            "generated_at": owners.get("generated_at"),
        },
        "inventory": sorted(str(p) for p in iter_sync_files(composite_dir)),
    }


def verify(
    composite_dir: Path,
    receipt: dict | None,
    drop_threshold: float = DROP_THRESHOLD,
) -> VerifyReport:
    baseline_at = receipt.get("deployed_at") if receipt else None
    try:
        fresh = snapshot(composite_dir)
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        detail = f"composite unreadable at {composite_dir}: {e}"
        return VerifyReport((Check("composite", False, detail),), baseline_at, None)

    if receipt is None:
        checks = [Check("baseline", True, "no deploy receipt yet — reporting only")]
        for fips, counts in sorted(fresh["state_counts"].items()):
            detail = ", ".join(f"{k} {counts[k]:,}" for k in _COUNT_KINDS)
            checks.append(Check(f"counts:{fips}", True, detail))
        o = fresh["owners"]
        checks.append(Check("owners", True, f"schema v{o['schema_version']}, {o['count']:,} rows"))
        checks.append(Check("inventory", True, f"{len(fresh['inventory'])} files to ship"))
        return VerifyReport(tuple(checks), None, fresh)

    checks: list[Check] = []
    for fips, base in sorted(receipt["state_counts"].items()):
        now = fresh["state_counts"].get(fips)
        if now is None:
            checks.append(Check(f"counts:{fips}", False, "state missing from fresh composite"))
            continue
        for kind in _COUNT_KINDS:
            b, n = base.get(kind, 0), now.get(kind, 0)
            ok = n >= b * (1 - drop_threshold)
            detail = f"{b:,} → {n:,}"
            if not ok:
                detail += f" — drop exceeds {drop_threshold:.0%} threshold"
            checks.append(Check(f"counts:{fips}:{kind}", ok, detail))

    base_o, new_o = receipt["owners"], fresh["owners"]
    ok = new_o["schema_version"] == base_o["schema_version"]
    detail = f"v{base_o['schema_version']} → v{new_o['schema_version']}"
    if not ok:
        detail += " — schema changed; confirm the backend declares support"
    checks.append(Check("owners:schema", ok, detail))
    b, n = base_o.get("count") or 0, new_o.get("count") or 0
    ok = n >= b * (1 - drop_threshold)
    detail = f"{b:,} → {n:,} rows"
    if not ok:
        detail += f" — drop exceeds {drop_threshold:.0%} threshold"
    checks.append(Check("owners:count", ok, detail))

    missing = sorted(set(receipt["inventory"]) - set(fresh["inventory"]))
    if missing:
        shown = ", ".join(missing[:5]) + ("…" if len(missing) > 5 else "")
        checks.append(Check("inventory", False, f"{len(missing)} deployed file(s) gone: {shown}"))
    else:
        checks.append(
            Check("inventory", True, f"all {len(receipt['inventory'])} deployed files present")
        )
    return VerifyReport(tuple(checks), baseline_at, fresh)


def load_receipt(path: Path | None = None) -> dict | None:
    path = path if path is not None else RECEIPT_PATH
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def write_receipt(fresh: dict, path: Path | None = None) -> dict:
    """Record what shipped (the verified snapshot) as the next verify's
    baseline. Atomic temp + rename, like every other manifest write."""
    path = Path(path if path is not None else RECEIPT_PATH)
    receipt = {
        "schema_version": 1,
        "deployed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        **fresh,
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(receipt, indent=2))
    tmp.rename(path)
    return receipt
