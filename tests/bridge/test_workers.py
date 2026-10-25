"""Worker helpers: jobs run off the UI thread, and serial jobs run in order."""

import threading

from PySide6.QtCore import QObject

from recon.bridge.workers import serial_submit
from tests.ui.qml_harness import app, wait_until


def test_serial_jobs_run_in_order_off_the_ui_thread() -> None:
    app()
    owner = QObject()
    submit = serial_submit(owner)
    order: list[int] = []
    threads: set[int] = set()

    def job(n: int) -> None:
        threads.add(threading.get_ident())
        order.append(n)

    for n in range(20):
        submit(lambda n=n: job(n))

    assert wait_until(lambda: len(order) == 20)
    assert order == list(range(20))
    assert threading.get_ident() not in threads
    assert len(threads) == 1
