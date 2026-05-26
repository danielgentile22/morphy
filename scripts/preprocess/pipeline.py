"""Pipeline + PipelineStep — orchestration shape for ``run_all``.

Replaces what was previously ~80 lines of imperative try/except in
``runner.run_all``. Each step:
  - declares its severity (REQUIRED fails the run; AUXILIARY logs a
    warning and continues),
  - decides whether it's applicable to the current `RunOutcome`,
  - does its work, populating the outcome.

The driver is the entire orchestration policy: severity handling,
progress emission, and per-step skip filtering live in one place. Adding
a step (e.g. Slice F's chunked compose) is a registration, not an edit
to the orchestrator body.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Protocol

log = logging.getLogger("preprocess.pipeline")

if TYPE_CHECKING:
    from .manifest import PreprocessManifest
    from .runner import RunOutcome

ProgressCallback = Callable[[str, str, dict], None]


class Severity(Enum):
    REQUIRED = "required"
    AUXILIARY = "auxiliary"


class PipelineStep(Protocol):
    """One step in a ``Pipeline``. Implementations should be small —
    a step is a thin wrapper around an existing ``run_…`` function that
    populates the outcome."""

    name: str
    severity: Severity

    def is_applicable(self, outcome: "RunOutcome") -> bool: ...
    def run(
        self,
        outcome: "RunOutcome",
        manifest: "PreprocessManifest",
        *,
        progress_callback: ProgressCallback | None,
    ) -> None: ...


@dataclass
class Pipeline:
    """Run a list of ``PipelineStep`` in order against one ``RunOutcome``.

    Skipped steps (either via ``skip`` or because their ``is_applicable``
    returns False) emit a ``step_skip`` progress event. Required-step
    failures populate ``outcome.failed_steps`` and propagate by setting
    fields on the outcome; auxiliary-step failures are logged at WARNING
    and don't affect the outcome's pass/fail.
    """

    steps: list[PipelineStep] = field(default_factory=list)

    def run(
        self,
        *,
        outcome: "RunOutcome",
        manifest: "PreprocessManifest",
        progress_callback: ProgressCallback | None = None,
        skip: set[str] = frozenset(),
    ) -> "RunOutcome":
        t0 = time.monotonic()
        for step in self.steps:
            if step.name in skip:
                _emit(progress_callback, "step_skip", step.name, {"reason": "skipped"})
                continue
            if not step.is_applicable(outcome):
                _emit(
                    progress_callback,
                    "step_skip",
                    step.name,
                    {"reason": "not applicable"},
                )
                continue
            _emit(progress_callback, "step_start", step.name, {})
            try:
                step.run(outcome, manifest, progress_callback=progress_callback)
                _emit(progress_callback, "step_ok", step.name, {})
            except Exception as exc:  # noqa: BLE001 — step-level catch is the policy
                msg = f"step {step.name} failed: {exc}"
                if step.severity == Severity.REQUIRED:
                    log.error(msg)
                    outcome.failed_steps.append(step.name)
                else:
                    log.warning(msg)
                _emit(
                    progress_callback,
                    "step_fail",
                    step.name,
                    {"error": str(exc), "severity": step.severity.value},
                )
        outcome.duration_seconds = time.monotonic() - t0
        return outcome


def _emit(
    cb: ProgressCallback | None, phase: str, key: str, info: dict
) -> None:
    if cb is None:
        return
    try:
        cb(phase, key, info)
    except Exception as e:  # noqa: BLE001 — UI callbacks must never abort the pipeline
        log.warning("progress callback raised: %s", e)
