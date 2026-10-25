"""Running bridge jobs off the UI thread (the UI thread never blocks)."""

from collections.abc import Callable

from PySide6.QtCore import QObject, QThreadPool

type Submit = Callable[[Callable[[], None]], None]
"""Runs a job off the UI thread; tests pass a synchronous one."""


def thread_pool_submit(job: Callable[[], None]) -> None:
    """Run `job` on Qt's global thread pool, off the UI thread."""
    QThreadPool.globalInstance().start(job)


def serial_submit(parent: QObject) -> Submit:
    """A Submit that runs jobs one at a time, in order, on a private worker thread.

    Session writes use this so a title save, a new block and "Next task" land
    in the order Tyler did them.
    """
    pool = QThreadPool(parent)
    pool.setMaxThreadCount(1)

    def submit(job: Callable[[], None]) -> None:
        pool.start(job)

    return submit
