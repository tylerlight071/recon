"""Load the Theme singleton into a QML engine so tests can read and set it."""

import re
from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine

UI_DIR = Path(__file__).resolve().parents[2] / "recon" / "ui"
THEME_DIR = UI_DIR / "theme"
THEME_QML = THEME_DIR / "Theme.qml"
_app: QGuiApplication | None = None
_COLOR = re.compile(r'readonly property color (\w+): "(#[0-9a-fA-F]{6})"')


def literal_colours() -> dict[str, str]:
    """Every colour token Theme.qml defines as a literal hex value."""
    return dict(_COLOR.findall(THEME_QML.read_text(encoding="utf-8")))


def load_theme() -> tuple[QQmlEngine, QObject]:
    """A fresh engine and its Theme singleton instance.

    Returns:
        The engine (keep it alive while using the theme) and the singleton.

    Raises:
        RuntimeError: The theme failed to load.
        TypeError: The probe didn't expose the singleton.
    """
    global _app  # noqa: PLW0603 - one app per process; keep it from being garbage-collected
    if QGuiApplication.instance() is None:
        _app = QGuiApplication([])
    engine = QQmlEngine()
    source = (
        "import QtQuick\n"
        f'import "{THEME_DIR.as_uri()}"\n'
        "QtObject { property QtObject theme: Theme }"
    )
    component = QQmlComponent(engine)
    component.setData(source.encode(), QUrl.fromLocalFile(str(UI_DIR / "probe.qml")))
    probe = component.create()
    if probe is None:
        errors = "; ".join(error.toString() for error in component.errors())
        msg = f"Theme.qml didn't load: {errors}"
        raise RuntimeError(msg)
    theme = probe.property("theme")
    if not isinstance(theme, QObject):
        msg = "Theme singleton missing"
        raise TypeError(msg)
    probe.setParent(engine)
    return engine, theme
