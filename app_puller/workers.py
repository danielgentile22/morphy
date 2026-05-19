"""QThread workers for background check / fetch operations.

We do all network I/O on background threads so the UI stays responsive
and the progress bar updates smoothly. Workers communicate with the UI
exclusively via Qt signals — no shared mutable state.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from fetch.base import DataSource
from fetch.manifest import Manifest
from fetch.puller import check_one, fetch_one
from PySide6.QtCore import QObject, QThread, Signal

CHECK_PARALLELISM = 8


class CheckWorker(QObject):
    """Check remote_version() for every source. Emits per-source updates."""

    progress = Signal(str, str)  # (source_id, status_text)
    one_done = Signal(str, bool, str)  # (source_id, ok, remote_version_or_error)
    all_done = Signal()

    def __init__(self, sources: list[DataSource], manifest: Manifest) -> None:
        super().__init__()
        self._sources = sources
        self._manifest = manifest
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            for s in self._sources:
                self.progress.emit(s.id, f"Checking {s.name}…")

            with ThreadPoolExecutor(max_workers=CHECK_PARALLELISM) as ex:
                futures = {ex.submit(check_one, s, self._manifest): s for s in self._sources}
                for fut in as_completed(futures):
                    if self._cancel:
                        for pending in futures:
                            pending.cancel()
                        break
                    s = futures[fut]
                    outcome = fut.result()
                    self.one_done.emit(
                        s.id,
                        outcome.ok,
                        outcome.remote_version or outcome.error or "",
                    )
            self._manifest.set_last_full_check()
            self._manifest.save()
        finally:
            self.all_done.emit()


class FetchWorker(QObject):
    """Fetch one or more sources sequentially.

    Sequential rather than parallel — the user explicitly chose 'one at a
    time' mental model, the progress bar is single-track, and several
    sources hit the same publisher (FCC) so parallel pulls would just
    rate-limit ourselves.
    """

    progress = Signal(str, int, int, str)
    # (source_id, bytes_done, bytes_total_or_-1, filename)

    started = Signal(str, str)  # (source_id, source_name)
    one_done = Signal(str, bool, str)  # (source_id, ok, message)
    all_done = Signal()

    def __init__(self, sources: list[DataSource], manifest: Manifest) -> None:
        super().__init__()
        self._sources = sources
        self._manifest = manifest
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            for s in self._sources:
                if self._cancel:
                    break

                self.started.emit(s.id, s.name)

                def _progress(done: int, total: int | None, fname: str, _sid=s.id) -> None:
                    self.progress.emit(_sid, done, total if total is not None else -1, fname)

                outcome = fetch_one(
                    s,
                    self._manifest,
                    _progress,
                    cancel_check=lambda: self._cancel,
                )

                if outcome.skipped:
                    msg = outcome.skip_reason or "Skipped."
                    self.one_done.emit(s.id, True, msg)
                elif outcome.ok:
                    self.one_done.emit(
                        s.id,
                        True,
                        f"Pulled {outcome.bytes:,} bytes (version {outcome.remote_version}).",
                    )
                else:
                    self.one_done.emit(s.id, False, outcome.error or "Failed.")
                self._manifest.save()
        finally:
            self.all_done.emit()


def make_thread(worker: QObject) -> QThread:
    """Wrap a QObject worker in a QThread and return both as a pair."""
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)  # type: ignore[attr-defined]
    # Caller is responsible for calling thread.start() and managing teardown.
    return thread


class PreprocessWorker(QObject):
    """Run preprocess.run_all() on a background thread, streaming progress.

    The preprocess framework's progress callback fires per phase; we re-emit
    each one as a Qt signal so the dialog can update rows in real time.
    """

    progress = Signal(str, str, dict)
    # (phase, key, info_dict)
    all_done = Signal(bool, dict)
    # (success, outcome_dict)

    def __init__(
        self,
        *,
        state_fips: str | None = None,
        force_rebuild: bool = False,
    ) -> None:
        super().__init__()
        self._state_fips = state_fips
        self._force_rebuild = force_rebuild
        self._cancel = False

    def cancel(self) -> None:
        # The preprocess runner doesn't currently expose mid-run cancel; the
        # flag here is reserved for a future "stop after current source" hook.
        self._cancel = True

    def run(self) -> None:
        # Import here so PreprocessWorker can sit in workers.py without
        # forcing the preprocess package to load until the user clicks the
        # button (keeps app startup fast).
        import sys
        from pathlib import Path

        scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        success = True
        outcome_data: dict = {}
        try:
            from preprocess import registry  # noqa: F401 — register everything
            from preprocess.runner import run_all

            def _cb(phase: str, key: str, info: dict) -> None:
                self.progress.emit(phase, key, info or {})

            outcome = run_all(
                state_fips=self._state_fips,
                force_rebuild=self._force_rebuild,
                progress_callback=_cb,
            )
            outcome_data = {
                "duration_seconds": outcome.duration_seconds,
                "normalized_ok": outcome.normalized_ok,
                "normalized_failed": outcome.normalized_failed,
                "normalized_skipped": outcome.normalized_skipped,
                "normalized_unavailable": outcome.normalized_unavailable,
                "composed_ok": outcome.composed_ok,
                "composed_failed": outcome.composed_failed,
            }
            success = len(outcome.normalized_failed) == 0 and len(outcome.composed_failed) == 0
        except Exception as e:
            success = False
            outcome_data = {"error": f"{type(e).__name__}: {e}"}
            self.progress.emit("error", "", {"error": str(e)})
        finally:
            self.all_done.emit(success, outcome_data)
