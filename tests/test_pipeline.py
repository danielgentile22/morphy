"""Tests for the Pipeline driver — the orchestration shape that replaced
the inline try/except blocks in run_all.

Verifies:
  - Steps run in order; each emits step_start + step_ok progress events.
  - A REQUIRED-step failure populates `failed_steps` and emits step_fail
    with severity=required.
  - An AUXILIARY-step failure does NOT populate `failed_steps`; it emits
    step_fail with severity=auxiliary.
  - Skipping by name emits step_skip with reason=skipped.
  - is_applicable=False emits step_skip with reason="not applicable".
  - Duration is set on the outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from preprocess.pipeline import Pipeline, Severity
from preprocess.runner import RunOutcome


@dataclass
class _RecordedStep:
    """Test double — a minimal PipelineStep that records when run() fired."""

    name: str
    severity: Severity = Severity.REQUIRED
    applicable: bool = True
    raise_on_run: BaseException | None = None
    ran: bool = False

    def is_applicable(self, outcome):
        return self.applicable

    def run(self, outcome, manifest, *, progress_callback):
        self.ran = True
        if self.raise_on_run is not None:
            raise self.raise_on_run


def _collect_events():
    events: list[tuple[str, str, dict]] = []

    def cb(phase, key, info):
        events.append((phase, key, info))

    return events, cb


def test_pipeline_runs_steps_in_order_with_events():
    steps = [_RecordedStep("a"), _RecordedStep("b"), _RecordedStep("c")]
    events, cb = _collect_events()
    outcome = RunOutcome()
    Pipeline(steps=steps).run(
        outcome=outcome, manifest=None, progress_callback=cb
    )
    assert [s.ran for s in steps] == [True, True, True]
    phases = [(e[0], e[1]) for e in events]
    # start/ok in order
    assert phases == [
        ("step_start", "a"),
        ("step_ok", "a"),
        ("step_start", "b"),
        ("step_ok", "b"),
        ("step_start", "c"),
        ("step_ok", "c"),
    ]
    assert outcome.failed_steps == []
    assert outcome.duration_seconds >= 0


def test_required_step_failure_records_in_outcome():
    boom = _RecordedStep(
        "boom",
        severity=Severity.REQUIRED,
        raise_on_run=RuntimeError("kaboom"),
    )
    after = _RecordedStep("after")
    events, cb = _collect_events()
    outcome = RunOutcome()
    Pipeline(steps=[boom, after]).run(
        outcome=outcome, manifest=None, progress_callback=cb
    )
    assert outcome.failed_steps == ["boom"]
    assert after.ran is True  # pipeline keeps going after a required failure
    fail_events = [e for e in events if e[0] == "step_fail"]
    assert len(fail_events) == 1
    assert fail_events[0][1] == "boom"
    assert fail_events[0][2]["severity"] == "required"
    assert "kaboom" in fail_events[0][2]["error"]


def test_auxiliary_step_failure_does_not_pollute_outcome():
    aux = _RecordedStep(
        "aux",
        severity=Severity.AUXILIARY,
        raise_on_run=RuntimeError("soft"),
    )
    events, cb = _collect_events()
    outcome = RunOutcome()
    Pipeline(steps=[aux]).run(
        outcome=outcome, manifest=None, progress_callback=cb
    )
    assert outcome.failed_steps == []  # auxiliary failures are warnings only
    fail_events = [e for e in events if e[0] == "step_fail"]
    assert fail_events[0][2]["severity"] == "auxiliary"


def test_skip_by_name_skips_with_reason():
    a, b = _RecordedStep("a"), _RecordedStep("b")
    events, cb = _collect_events()
    Pipeline(steps=[a, b]).run(
        outcome=RunOutcome(),
        manifest=None,
        progress_callback=cb,
        skip={"a"},
    )
    assert a.ran is False
    assert b.ran is True
    skip_events = [e for e in events if e[0] == "step_skip"]
    assert skip_events == [("step_skip", "a", {"reason": "skipped"})]


def test_inapplicable_step_skipped_with_reason():
    a = _RecordedStep("a", applicable=False)
    events, cb = _collect_events()
    Pipeline(steps=[a]).run(
        outcome=RunOutcome(), manifest=None, progress_callback=cb
    )
    assert a.ran is False
    assert (
        "step_skip",
        "a",
        {"reason": "not applicable"},
    ) in events


def test_progress_callback_exceptions_do_not_abort_pipeline():
    def bad_cb(phase, key, info):
        raise RuntimeError("callback explode")

    a = _RecordedStep("a")
    Pipeline(steps=[a]).run(
        outcome=RunOutcome(), manifest=None, progress_callback=bad_cb
    )
    assert a.ran is True  # pipeline still ran the step


# ── Standard pipeline steps — smoke-level shape checks ────────────────────


def test_default_pipeline_steps_have_expected_names_and_severities():
    from preprocess.pipeline import (
        AppAssetsStep,
        ComposeStatesStep,
        NormalizeAllStep,
        TilesStep,
    )

    assert NormalizeAllStep().severity == Severity.REQUIRED
    assert ComposeStatesStep().severity == Severity.REQUIRED
    assert AppAssetsStep().severity == Severity.AUXILIARY
    assert TilesStep().severity == Severity.AUXILIARY
    assert {NormalizeAllStep().name, ComposeStatesStep().name, AppAssetsStep().name, TilesStep().name} == {
        "normalize_all",
        "compose",
        "app_assets",
        "tiles",
    }


def test_tiles_step_inapplicable_when_no_composed_states():
    from preprocess.pipeline import TilesStep

    outcome = RunOutcome()  # composed_ok empty
    assert TilesStep().is_applicable(outcome) is False
    outcome.composed_ok.append("05")
    assert TilesStep().is_applicable(outcome) is True
