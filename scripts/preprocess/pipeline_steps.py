"""Concrete pipeline steps for the standard ``run_all`` pipeline.

Each step is a thin wrapper over an existing ``run_…`` function. The
heavy lifting (manifest writes, per-source progress events, etc.) still
happens inside those functions — the steps exist to express *what*
``run_all`` does in a declarative shape and to centralise severity +
applicability policy.

The CLI / Qt UI still see the same per-source phase events
(``normalize_start``, ``compose_ok``, …) emitted by the inner
``run_normalize_all`` / ``run_compose_all``; the pipeline adds
``step_start`` / ``step_ok`` / ``step_fail`` / ``step_skip`` around
them. A streaming UI can layer the two together.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .pipeline import PipelineStep, Severity

if TYPE_CHECKING:
    from .geographies import StateGeography
    from .manifest import PreprocessManifest
    from .runner import RunOutcome

ProgressCallback = Callable[[str, str, dict], None]


@dataclass
class NormalizeAllStep(PipelineStep):
    name: str = "normalize_all"
    severity: Severity = Severity.REQUIRED
    force_rebuild: bool = False

    def is_applicable(self, outcome: "RunOutcome") -> bool:
        return True

    def run(
        self,
        outcome: "RunOutcome",
        manifest: "PreprocessManifest",
        *,
        progress_callback: ProgressCallback | None,
    ) -> None:
        # Inner function emits per-source events (normalize_start/ok/fail/…)
        # — the pipeline layer wraps those with step_start/ok.
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
class ComposeStatesStep(PipelineStep):
    name: str = "compose"
    severity: Severity = Severity.REQUIRED
    # When None, the step picks every state with normalized parcel data.
    states: list["StateGeography"] | None = None

    def is_applicable(self, outcome: "RunOutcome") -> bool:
        return True

    def run(
        self,
        outcome: "RunOutcome",
        manifest: "PreprocessManifest",
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
class AppAssetsStep(PipelineStep):
    """Refresh composite/index.json + per-state county boundaries +
    facets + slim parquets. Auxiliary: failure logs a warning, the
    composite output on disk is still useful."""

    name: str = "app_assets"
    severity: Severity = Severity.AUXILIARY

    def is_applicable(self, outcome: "RunOutcome") -> bool:
        return True

    def run(
        self,
        outcome: "RunOutcome",
        manifest: "PreprocessManifest",
        *,
        progress_callback: ProgressCallback | None,
    ) -> None:
        from .app_assets import run_app_assets

        run_app_assets(progress_callback=progress_callback)


@dataclass
class TilesStep(PipelineStep):
    """Build parcels.pmtiles per composed state. Auxiliary: needs an
    external ``tippecanoe`` binary; absent or per-state failures are
    warnings, not errors."""

    name: str = "tiles"
    severity: Severity = Severity.AUXILIARY
    tile_failures: list[str] = field(default_factory=list)

    def is_applicable(self, outcome: "RunOutcome") -> bool:
        return bool(outcome.composed_ok)

    def run(
        self,
        outcome: "RunOutcome",
        manifest: "PreprocessManifest",
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
                import logging

                logging.getLogger("preprocess.pipeline").warning(
                    "tile generation failed for state %s: %s", fips, exc
                )
