"""Application set-up: the Qt app object, the QML engine and what it loads."""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlError
from PySide6.QtQuick import QQuickWindow
from shiboken6 import Shiboken

from recon.config import APP_ID, APP_NAME
from recon.services.qml_network import LocalOnlyNetworkFactory

UI_DIR = Path(__file__).resolve().parent / "ui"
MAIN_QML = UI_DIR / "MainWindow.qml"
PANEL_QML = UI_DIR / "PanelWindow.qml"
GALLERY_QML = UI_DIR / "screens" / "Gallery.qml"
STARTUP_PROBLEM_QML = UI_DIR / "StartupProblem.qml"

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class QmlEngine:
    """The app's single QML engine and the network factory it must outlive."""

    engine: QQmlApplicationEngine
    network: LocalOnlyNetworkFactory


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
    # Line numbers only: QML warning text can quote bound values (notes).
    for warning in warnings:
        _log.warning("qml warning at line %s", warning.line())


def create_engine(bridges: Mapping[str, QObject] | None = None) -> QmlEngine:
    """The one engine both windows share, so their state is always in sync.

    Args:
        bridges: Objects QML reaches by name, e.g. {"Navigation": navigation}.
            Attached per engine (not process-wide), so tests stay independent.

    Returns:
        The engine, with local-only network access and warning logging.
    """
    engine = QQmlApplicationEngine()
    network = LocalOnlyNetworkFactory()
    engine.setNetworkAccessManagerFactory(network)
    engine.warnings.connect(_log_qml_warnings)
    for name, bridge in (bridges or {}).items():
        engine.rootContext().setContextProperty(name, bridge)
    return QmlEngine(engine, network)


def load_qml(engine: QQmlApplicationEngine, path: Path) -> bool:
    """Load a top-level QML file into `engine`.

    Args:
        engine: The application's engine.
        path: The .qml file to load.

    Returns:
        True when it added a root object.
    """
    before = len(engine.rootObjects())
    engine.load(QUrl.fromLocalFile(str(path)))
    loaded = len(engine.rootObjects()) > before
    if not loaded:
        _log.error("qml file failed to load")
    return loaded


def load_windows(engine: QQmlApplicationEngine) -> bool:
    """Load the main window (shown) and the panel (hidden until a room opens).

    Returns:
        True when both loaded.
    """
    return load_qml(engine, MAIN_QML) and load_qml(engine, PANEL_QML)


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
