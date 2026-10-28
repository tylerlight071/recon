"""Running bridge jobs off the UI thread (the UI thread never blocks)."""

import logging
import queue
import threading
from collections.abc import Callable
from typing import Final

from PySide6.QtCore import QObject, QThreadPool

from recon.logging_setup import Safe

type Submit = Callable[[Callable[[], None]], None]
"""Runs a job off the UI thread; tests pass a synchronous one."""

_log = logging.getLogger(__name__)

DRAIN_MS: Final = 10_000
"""At quit, how long to wait for queued saves before closing anyway."""


def thread_pool_submit(job: Callable[[], None]) -> None:
    """Run `job` on Qt's global thread pool, off the UI thread."""
    QThreadPool.globalInstance().start(job)


class SerialWorker:
    """Runs jobs one at a time, in order, on a private worker thread.

    Session writes use this so a title save, a new block and "Next task" land in
    the order the user did them. Call it like a Submit; `drain()` at quit waits for
    every queued job, so nothing is still waiting when the database closes.
    """

    def __init__(self, parent: QObject) -> None:
        """Create the worker thread's pool, owned by `parent`."""
        self._pool = QThreadPool(parent)
        self._pool.setMaxThreadCount(1)

    def __call__(self, job: Callable[[], None]) -> None:
        """Queue `job`."""
        self._pool.start(job)

    def drain(self, timeout_ms: int = DRAIN_MS) -> bool:
        """Wait for every queued job. Returns False if they didn't finish in time."""
        return self._pool.waitForDone(timeout_ms)


class DaemonWorker:
    """Runs jobs one at a time, in order, on a daemon thread that never delays quitting.

    For processing (task 2.5): a model call can take minutes and can't be
    interrupted, so waiting for it at quit would hang the app. Its jobs check a
    cancel flag between steps instead, and anything it was doing is safe to cut
    off (the room stays queued, and nothing reaches the vault before Apply).
    """

    def __init__(self, name: str) -> None:
        """Create the worker (the thread starts with the first job)."""
        self._jobs: queue.SimpleQueue[Callable[[], None] | None] = queue.SimpleQueue()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)

    def __call__(self, job: Callable[[], None]) -> None:
        """Queue `job`."""
        if not self._thread.is_alive():
            self._thread.start()
        self._jobs.put(job)

    def close(self) -> None:
        """Stop after the current job (without waiting for it)."""
        self._jobs.put(None)

    def _run(self) -> None:
        while (job := self._jobs.get()) is not None:
            # Thread boundary: jobs report their own errors; this keeps the worker alive.
            try:
                job()
            except Exception as exc:  # thread boundary
                _log.error("background job failed: %s", Safe(type(exc).__name__))


def drain_global_pool(timeout_ms: int = DRAIN_MS) -> bool:
    """Wait for jobs on Qt's global pool (Start, pinning) at quit."""
    return QThreadPool.globalInstance().waitForDone(timeout_ms)
