"""UI test isolation: no window, timer or focus leaks from one test into the next."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication


@pytest.fixture(autouse=True)
def close_windows() -> Iterator[None]:
    yield
    if QGuiApplication.instance() is None:
        return
    for window in QGuiApplication.topLevelWindows():
        window.close()
        window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()
