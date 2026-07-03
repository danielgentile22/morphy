"""Refresh planner — the pure decision brain of the refresh flow (#238).

Maps (source registry, fetch manifest, preprocess-manifest composite
state) to a plan: which sources need pulling, which states need
preprocessing given what was pulled, and whether prod needs a deploy
afterwards (PRD #233 module 3). No network, no UI — unit-testable
exhaustively. Staleness vocabulary is ``freshness.badge_for``, so the
pull plan and the table badges can never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fetch.base import DataSource
from fetch.manifest import Manifest, SourceEntry
from preprocess.geographies import STATES
from preprocess.manifest import NormalizeEntry, PreprocessManifest

from .freshness import badge_for

_NAME_TO_FIPS = {g.name.lower(): g.fips for g in STATES.values()}


@dataclass(frozen=True)
class RefreshPlan:
    pull_sources: tuple[str, ...]  # auto sources whose badge reads stale/missing
    preprocess_states: tuple[str, ...]  # FIPS to preselect in the preprocess picker
    candidate_states: tuple[str, ...]  # every FIPS the picker should offer
    deploy_warranted: bool  # some fresh composite predates a pull


def state_fips_for_source(source: DataSource) -> str | None:
    """FIPS for single-state sources, parsed from the declared coverage
    string ("State: West Virginia (55 counties)" → "54"). None = national.
    """
    cov = getattr(source, "coverage", "") or ""
    if not cov.startswith("State:"):
        return None
    name = cov.split(":", 1)[1].split("(")[0].strip()
    return _NAME_TO_FIPS.get(name.lower())


def plan_pulls(sources: list[DataSource], manifest: Manifest) -> list[str]:
    """Auto-pullable sources whose badge reads stale or missing — the
    predicate behind the TUI's pull-all-stale."""
    out: list[str] = []
    for s in sources:
        entry = manifest.sources.get(s.id) or SourceEntry()
        if badge_for(s, entry).kind not in ("stale", "missing"):
            continue
        if s.is_manual_only:
            continue
        if s.needs_credentials and not s.credentials_available():
            continue
        out.append(s.id)
    return out


def plan_refresh(
    sources: list[DataSource],
    manifest: Manifest,
    pre: PreprocessManifest,
) -> RefreshPlan:
    """Pure plan: pulls due, states to preprocess, deploy warranted.

    A state needs preprocessing when an installed source touching it has
    raw data the normalizer hasn't consumed yet (local_version diverged
    from the normalize entry's raw_local_version) — which is exactly the
    state a just-finished pull leaves behind. National sources touch
    every composed state.
    """
    composed_ok = {f for f, c in pre.composed.items() if c.status == "ok"}
    candidates: set[str] = set(composed_ok)
    for norm in pre.normalized.values():
        candidates.update(norm.states_covered)
    preselect: set[str] = set()
    deploy = False
    for s in sources:
        entry = manifest.sources.get(s.id)
        if entry is None or not entry.is_installed():
            continue
        fips = state_fips_for_source(s)
        if fips:
            candidates.add(fips)
        if _needs_preprocess(entry, pre.normalized.get(s.id)):
            preselect.update({fips} if fips else composed_ok)
        deploy = deploy or _pull_newer_than_composite(entry, fips, pre, composed_ok)
    return RefreshPlan(
        pull_sources=tuple(plan_pulls(sources, manifest)),
        preprocess_states=tuple(sorted(preselect)),
        candidate_states=tuple(sorted(candidates)),
        deploy_warranted=deploy,
    )


def _needs_preprocess(entry: SourceEntry, norm: NormalizeEntry | None) -> bool:
    """Raw on disk is ahead of what the normalizer last consumed.
    "skipped" counts as consumed — it means the last run found the
    output already fresh (mirrors ``is_normalize_fresh``)."""
    if norm is None or norm.status not in ("ok", "skipped"):
        return True
    return norm.raw_local_version != entry.local_version


def _pull_newer_than_composite(
    entry: SourceEntry,
    fips: str | None,
    pre: PreprocessManifest,
    composed_ok: set[str],
) -> bool:
    fetched = _parse_ts(entry.fetched_at)
    if fetched is None:
        return False
    for f in ({fips} if fips else composed_ok) & composed_ok:
        composed_at = _parse_ts(pre.composed[f].preprocessed_at)
        if composed_at is not None and composed_at < fetched:
            return True
    return False


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
