"""Pipeline runner + the step types ``run_all`` orchestrates.

The driver (:class:`Pipeline`) is the entire orchestration policy:
severity handling, progress emission, per-step skip filtering live in
one place. Each step:
  - declares its severity (REQUIRED fails the run; AUXILIARY logs a
    warning and continues),
  - decides whether it's applicable to the current `RunOutcome`,
  - does its work, populating the outcome.

Adding a new step is one registration in ``runner.run_all`` + one
class below — no edit to the driver body. Inner per-source events
(``normalize_start``, ``compose_ok``, …) still flow from the underlying
``run_…`` functions; the pipeline adds ``step_start`` / ``step_ok`` /
``step_fail`` / ``step_skip`` around them.
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
    from .geographies import StateGeography
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

    def is_applicable(self, outcome: RunOutcome) -> bool: ...
    def run(
        self,
        outcome: RunOutcome,
        manifest: PreprocessManifest,
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
        outcome: RunOutcome,
        manifest: PreprocessManifest,
        progress_callback: ProgressCallback | None = None,
        skip: set[str] = frozenset(),
    ) -> RunOutcome:
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


def _emit(cb: ProgressCallback | None, phase: str, key: str, info: dict) -> None:
    if cb is None:
        return
    try:
        cb(phase, key, info)
    except Exception as e:  # noqa: BLE001 — UI callbacks must never abort the pipeline
        log.warning("progress callback raised: %s", e)


# ── Concrete steps ─────────────────────────────────────────────────────────


@dataclass
class NormalizeAllStep:
    name: str = "normalize_all"
    severity: Severity = Severity.REQUIRED
    force_rebuild: bool = False

    def is_applicable(self, outcome: RunOutcome) -> bool:
        return True

    def run(
        self,
        outcome: RunOutcome,
        manifest: PreprocessManifest,
        *,
        progress_callback: ProgressCallback | None,
    ) -> None:
        from .runner import run_normalize_all

        statuses = run_normalize_all(
            manifest,
            force_rebuild=self.force_rebuild,
            progress_callback=progress_callback,
        )
        for sid, st in statuses.items():
            if st == "ok":
                outcome.normalized_ok.append(sid)
            elif st == "failed":
                outcome.normalized_failed.append(sid)
            elif st == "skipped":
                outcome.normalized_skipped.append(sid)
            else:
                outcome.normalized_unavailable.append(sid)


@dataclass
class ComposeStatesStep:
    name: str = "compose"
    severity: Severity = Severity.REQUIRED
    # When None, the step picks every state with normalized parcel data.
    states: list[StateGeography] | None = None

    def is_applicable(self, outcome: RunOutcome) -> bool:
        return True

    def run(
        self,
        outcome: RunOutcome,
        manifest: PreprocessManifest,
        *,
        progress_callback: ProgressCallback | None,
    ) -> None:
        from .runner import _states_with_normalized_parcel_data, run_compose_all

        states = (
            self.states
            if self.states is not None
            else _states_with_normalized_parcel_data(manifest)
        )
        results = run_compose_all(
            manifest,
            states=states,
            progress_callback=progress_callback,
        )
        for fips, res in results.items():
            if res is None:
                outcome.composed_failed.append(fips)
            else:
                outcome.composed_ok.append(fips)


@dataclass
class AppAssetsStep:
    """Refresh composite/index.json + per-state county boundaries +
    facets + slim parquets. Auxiliary: failure logs a warning, the
    composite output on disk is still useful."""

    name: str = "app_assets"
    severity: Severity = Severity.AUXILIARY

    def is_applicable(self, outcome: RunOutcome) -> bool:
        return True

    def run(
        self,
        outcome: RunOutcome,
        manifest: PreprocessManifest,
        *,
        progress_callback: ProgressCallback | None,
    ) -> None:
        from .app_assets import run_app_assets

        run_app_assets(progress_callback=progress_callback)


@dataclass
class OwnersIndexStep:
    """Write the cross-state owners index (composite/owners_index.json)
    from the slim per-state parcels_attr.parquet that AppAssetsStep
    produced. Auxiliary: a failure leaves the per-state composites and
    map app fully usable, only the Lead backend's index is stale."""

    name: str = "owners_index"
    severity: Severity = Severity.AUXILIARY

    def is_applicable(self, outcome: RunOutcome) -> bool:
        return bool(outcome.composed_ok)

    def run(
        self,
        outcome: RunOutcome,
        manifest: PreprocessManifest,
        *,
        progress_callback: ProgressCallback | None,
    ) -> None:
        from .owners_index import run_owners_index

        run_owners_index(progress_callback=progress_callback)


@dataclass
class TilesStep:
    """Build parcels.pmtiles per composed state. Auxiliary: needs an
    external ``tippecanoe`` binary; absent or per-state failures are
    warnings, not errors."""

    name: str = "tiles"
    severity: Severity = Severity.AUXILIARY
    tile_failures: list[str] = field(default_factory=list)

    def is_applicable(self, outcome: RunOutcome) -> bool:
        return bool(outcome.composed_ok)

    def run(
        self,
        outcome: RunOutcome,
        manifest: PreprocessManifest,
        *,
        progress_callback: ProgressCallback | None,
    ) -> None:
        from .tiles import build_state_tiles, tippecanoe_available

        if not tippecanoe_available():
            raise RuntimeError(
                "tippecanoe not installed — install it "
                "(brew install tippecanoe) or pass --skip-tiles"
            )
        for fips in sorted(set(outcome.composed_ok)):
            try:
                build_state_tiles(fips)
            except Exception as exc:  # noqa: BLE001 — per-state, never fatal
                self.tile_failures.append(fips)
                logging.getLogger("preprocess.pipeline").warning(
                    "tile generation failed for state %s: %s", fips, exc
                )
