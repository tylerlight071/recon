"""Running bridge jobs off the UI thread (the UI thread never blocks)."""

from collections.abc import Callable
from typing import Final

from PySide6.QtCore import QObject, QThreadPool

type Submit = Callable[[Callable[[], None]], None]
"""Runs a job off the UI thread; tests pass a synchronous one."""

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


def drain_global_pool(timeout_ms: int = DRAIN_MS) -> bool:
    """Wait for jobs on Qt's global pool (Start, pinning) at quit."""
    return QThreadPool.globalInstance().waitForDone(timeout_ms)
