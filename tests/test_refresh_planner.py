"""Refresh planner (#238): pure (registry, manifest, composite) → plan.

Covers the acceptance matrix: stale source → pull planned; pulled parcel
source → its state preselected; nothing pulled → no-op plan; fresh
composite older than pulls → deploy warranted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from data_tui.planner import plan_pulls, plan_refresh, state_fips_for_source
from fetch.legal import AutomationPolicy, CommercialUse, LegalInfo
from fetch.manifest import Manifest, SourceEntry
from preprocess.manifest import ComposeEntry, NormalizeEntry, PreprocessManifest

NOW = datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _legal(automation: AutomationPolicy = AutomationPolicy.ALLOWED) -> LegalInfo:
    return LegalInfo(
        publisher="x",
        license="x",
        license_url="x",
        automation=automation,
        commercial_use=CommercialUse.ALLOWED,
        manual_url="https://example.com",
    )


@dataclass
class FakeSource:
    id: str = "src"
    name: str = "Src"
    coverage: str = "National"
    update_cadence_days: int | None = 30
    legal: LegalInfo = field(default_factory=_legal)

    @property
    def is_manual_only(self) -> bool:
        return self.legal.automation == AutomationPolicy.MANUAL_ONLY

    @property
    def needs_credentials(self) -> bool:
        return self.legal.automation == AutomationPolicy.CREDENTIALED

    def credentials_available(self) -> bool:
        return False


def _installed_entry(
    version: str = "v1", fetched: datetime | None = None, cadence: int = 30
) -> SourceEntry:
    fetched = fetched or NOW
    return SourceEntry(
        local_version=version,
        remote_version=version,
        status="ok",
        fetched_at=_iso(fetched),
        update_cadence_days=cadence,
        next_recommended_check_at=_iso(fetched + timedelta(days=cadence)),
    )


def _manifest(entries: dict[str, SourceEntry]) -> Manifest:
    m = Manifest()
    m.sources = entries
    return m


def _norm(
    version: str = "v1", status: str = "ok", states: list[str] | None = None
) -> NormalizeEntry:
    return NormalizeEntry(
        raw_local_version=version,
        preprocessed_at=_iso(NOW),
        raw_rows=1,
        canonical_rows=1,
        bytes=1,
        states_covered=list(states or []),
        status=status,
    )


def _composed(at: datetime, status: str = "ok") -> ComposeEntry:
    return ComposeEntry(preprocessed_at=_iso(at), status=status)


def _pre(
    normalized: dict[str, NormalizeEntry] | None = None,
    composed: dict[str, ComposeEntry] | None = None,
) -> PreprocessManifest:
    return PreprocessManifest(normalized=normalized or {}, composed=composed or {})


WV = FakeSource(id="wv_parcels", name="WV Parcels", coverage="State: West Virginia")
NATIONAL = FakeSource(id="fcc_asr", name="FCC ASR")


# ── state_fips_for_source ────────────────────────────────────────────────


def test_state_fips_parsed_from_coverage():
    assert state_fips_for_source(WV) == "54"
    assert state_fips_for_source(FakeSource(coverage="State: Florida (all 67 counties)")) == "12"
    assert state_fips_for_source(NATIONAL) is None
    assert state_fips_for_source(FakeSource(coverage="State: Atlantis")) is None


# ── pull planning ────────────────────────────────────────────────────────


def test_stale_source_pull_planned():
    stale = _installed_entry(fetched=NOW - timedelta(days=90), cadence=7)
    assert plan_pulls([WV], _manifest({"wv_parcels": stale})) == ["wv_parcels"]


def test_missing_source_pull_planned():
    assert plan_pulls([WV], _manifest({})) == ["wv_parcels"]


def test_fresh_manual_and_credentialed_sources_not_pull_planned():
    manual = FakeSource(id="ar", legal=_legal(AutomationPolicy.MANUAL_ONLY))
    creds = FakeSource(id="regrid", legal=_legal(AutomationPolicy.CREDENTIALED))
    fresh = FakeSource(id="fresh")
    m = _manifest({"fresh": _installed_entry()})
    assert plan_pulls([manual, creds, fresh], m) == []


# ── preprocess-state preselection ────────────────────────────────────────


def test_pulled_parcel_source_preselects_its_state():
    """Pull bumped local_version past what the normalizer last consumed."""
    m = _manifest({"wv_parcels": _installed_entry("v2")})
    plan = plan_refresh([WV], m, _pre(normalized={"wv_parcels": _norm("v1")}))
    assert plan.preprocess_states == ("54",)
    assert "54" in plan.candidate_states


def test_never_normalized_installed_source_preselects_its_state():
    plan = plan_refresh([WV], _manifest({"wv_parcels": _installed_entry()}), _pre())
    assert plan.preprocess_states == ("54",)


def test_normalize_current_source_not_preselected():
    m = _manifest({"wv_parcels": _installed_entry("v1")})
    for status in ("ok", "skipped"):
        plan = plan_refresh([WV], m, _pre(normalized={"wv_parcels": _norm("v1", status=status)}))
        assert plan.preprocess_states == ()


def test_national_pull_preselects_all_composed_states():
    m = _manifest({"fcc_asr": _installed_entry("v2")})
    pre = _pre(
        normalized={"fcc_asr": _norm("v1")},
        composed={"05": _composed(NOW), "54": _composed(NOW)},
    )
    plan = plan_refresh([NATIONAL], m, pre)
    assert plan.preprocess_states == ("05", "54")


def test_nothing_pulled_is_noop_plan():
    m = _manifest({"wv_parcels": _installed_entry("v1", fetched=NOW - timedelta(days=1))})
    pre = _pre(
        normalized={"wv_parcels": _norm("v1", states=["54"])},
        composed={"54": _composed(NOW)},
    )
    plan = plan_refresh([WV], m, pre)
    assert plan.pull_sources == ()
    assert plan.preprocess_states == ()
    assert plan.deploy_warranted is False
    assert plan.candidate_states == ("54",)


# ── deploy warranted ─────────────────────────────────────────────────────


def test_fresh_composite_older_than_pull_warrants_deploy():
    m = _manifest({"wv_parcels": _installed_entry("v2", fetched=NOW)})
    pre = _pre(composed={"54": _composed(NOW - timedelta(days=1))})
    assert plan_refresh([WV], m, pre).deploy_warranted is True


def test_composite_newer_than_pull_does_not_warrant_deploy():
    m = _manifest({"wv_parcels": _installed_entry("v1", fetched=NOW - timedelta(days=1))})
    pre = _pre(
        normalized={"wv_parcels": _norm("v1")},
        composed={"54": _composed(NOW)},
    )
    assert plan_refresh([WV], m, pre).deploy_warranted is False


def test_state_pull_does_not_warrant_deploy_for_other_states():
    """WV pull leaves the AR composite alone; failed composites don't count."""
    m = _manifest({"wv_parcels": _installed_entry("v2", fetched=NOW)})
    pre = _pre(
        composed={
            "05": _composed(NOW - timedelta(days=1)),
            "54": _composed(NOW - timedelta(days=1), status="failed"),
        }
    )
    assert plan_refresh([WV], m, pre).deploy_warranted is False
