"""Application set-up: the Qt app object, the QML engine and what it loads."""

import logging
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlError
from PySide6.QtQuick import QQuickWindow
from shiboken6 import Shiboken

from recon.config import APP_ID, APP_NAME

UI_DIR = Path(__file__).resolve().parent / "ui"
GALLERY_QML = UI_DIR / "screens" / "Gallery.qml"

_log = logging.getLogger(__name__)


def create_application(argv: Sequence[str]) -> QGuiApplication:
    """Create the Qt application with Recon's identity.

    The desktop file name must be set before the app object exists, so the
    GlobalShortcuts portal and the KWin rule recognise Recon (ADR 0003).

    Args:
        argv: Arguments for Qt (normally just the program name).

    Returns:
        The application object.
    """
    QGuiApplication.setDesktopFileName(APP_ID)
    QGuiApplication.setApplicationName(APP_NAME)
    return QGuiApplication(list(argv))


def _log_qml_warnings(warnings: list[QQmlError]) -> None:
    # Count and location only: QML warning text can quote bound values (notes).
    for warning in warnings:
        _log.warning("qml warning at line %s", warning.line())


def load_qml(engine: QQmlApplicationEngine, path: Path) -> bool:
    """Load a top-level QML file into `engine`.

    Args:
        engine: The application's engine.
        path: The .qml file to load.

    Returns:
        True when it produced a root object.
    """
    engine.warnings.connect(_log_qml_warnings)
    engine.load(QUrl.fromLocalFile(str(path)))
    loaded = bool(engine.rootObjects())
    if not loaded:
        _log.error("qml file failed to load")
    return loaded


def root_window(engine: QQmlApplicationEngine, index: int = 0) -> QQuickWindow | None:
    """The engine's top-level QML window as a QQuickWindow.

    PySide returns QML `Window` roots typed as plain QWindow, which hides
    QQuickWindow API such as grabWindow(); this casts to the real type.

    Args:
        engine: An engine that has loaded a QML file with a Window root.
        index: Which root object, in load order.

    Returns:
        The window, or None if that root isn't a Qt Quick window.
    """
    roots = engine.rootObjects()
    if index >= len(roots) or not roots[index].inherits("QQuickWindow"):
        return None
    pointer = Shiboken.getCppPointer(roots[index])[0]
    window = Shiboken.wrapInstance(pointer, QQuickWindow)
    return window if isinstance(window, QQuickWindow) else None
