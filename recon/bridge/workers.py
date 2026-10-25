"""Running bridge jobs off the UI thread (the UI thread never blocks)."""

from collections.abc import Callable

from PySide6.QtCore import QThreadPool

type Submit = Callable[[Callable[[], None]], None]
"""Runs a job off the UI thread; tests pass a synchronous one."""


def thread_pool_submit(job: Callable[[], None]) -> None:
    """Run `job` on Qt's global thread pool, off the UI thread."""
    QThreadPool.globalInstance().start(job)
