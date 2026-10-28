"""Worker helpers: jobs run off the UI thread, in order, and drain at quit."""

import threading
import time

import pytest
from PySide6.QtCore import QObject

from recon.bridge.workers import (
    DaemonWorker,
    SerialWorker,
    drain_global_pool,
    thread_pool_submit,
)
from tests.ui.qml_harness import app, wait_until


def test_serial_jobs_run_in_order_off_the_ui_thread() -> None:
    app()
    owner = QObject()  # owns the pool; kept alive for the test
    worker = SerialWorker(owner)
    order: list[int] = []
    threads: set[int] = set()

    def job(n: int) -> None:
        threads.add(threading.get_ident())
        order.append(n)

    for n in range(20):
        worker(lambda n=n: job(n))

    assert wait_until(lambda: len(order) == 20)
    assert order == list(range(20))
    assert threading.get_ident() not in threads
    assert len(threads) == 1


def test_drain_waits_for_queued_jobs() -> None:
    app()
    owner = QObject()  # owns the pool; kept alive for the test
    worker = SerialWorker(owner)
    done: list[int] = []
    for n in range(3):
        worker(lambda n=n: (time.sleep(0.05), done.append(n)))

    assert worker.drain() is True
    assert done == [0, 1, 2]


def test_drain_reports_a_job_that_overruns() -> None:
    app()
    owner = QObject()  # owns the pool; kept alive for the test
    worker = SerialWorker(owner)
    release = threading.Event()
    worker(lambda: release.wait(2))

    assert worker.drain(timeout_ms=50) is False
    release.set()
    assert worker.drain() is True


def test_the_global_pool_drains_too() -> None:
    app()
    done: list[int] = []
    thread_pool_submit(lambda: (time.sleep(0.05), done.append(1)))

    assert drain_global_pool() is True
    assert done == [1]


def test_daemon_worker_runs_jobs_in_order_and_survives_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    worker = DaemonWorker("test-worker")
    seen: list[str] = []
    done = threading.Event()

    def boom() -> None:
        raise RuntimeError("boom")

    worker(lambda: seen.append(threading.current_thread().name))
    worker(boom)
    worker(lambda: seen.append("after"))
    worker(done.set)
    worker.close()

    assert done.wait(2)
    assert seen == ["test-worker", "after"]
    assert "background job failed: RuntimeError" in caplog.text
