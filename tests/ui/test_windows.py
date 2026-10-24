"""Task 1.3: the panel and main window share one engine and behave as the spec says."""

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QMetaObject, QObject
from PySide6.QtQuick import QQuickItem, QQuickWindow

from recon.app import QmlEngine, create_engine, load_windows, root_window
from recon.bridge.navigation import NavigationBridge
from recon.bridge.settings import SettingsBridge
from recon.config import Settings
from tests.ui.qml_harness import app, wait, wait_until


@dataclass
class Running:
    qml: QmlEngine
    settings: SettingsBridge
    navigation: NavigationBridge
    main: QQuickWindow
    panel: QQuickWindow
    warnings: list[str]
    saved: list[Settings]

    def find(self, window: QQuickWindow, name: str) -> QObject:
        # Walk the visual tree: Repeater delegates aren't QObject children of the window.
        pending: list[QQuickItem] = [window.contentItem()]
        while pending:
            item = pending.pop()
            if item.objectName() == name:
                return item
            pending.extend(item.childItems())
        raise AssertionError(name)


@pytest.fixture
def running(request: pytest.FixtureRequest) -> Iterator[Running]:
    app()
    width = getattr(request, "param", 420)
    owner = QObject()
    saved: list[Settings] = []
    settings = SettingsBridge(Settings(panel_width=width), saved.append, parent=owner)
    navigation = NavigationBridge(parent=owner)
    qml = create_engine({"AppSettings": settings, "Navigation": navigation})
    warnings: list[str] = []
    qml.engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
    assert load_windows(qml.engine)
    main, panel = root_window(qml.engine, 0), root_window(qml.engine, 1)
    assert main is not None
    assert panel is not None
    wait(50)
    yield Running(qml, settings, navigation, main, panel, warnings, saved)
    # The engine goes first: bindings must never re-run against deleted bridges.
    for window in (main, panel):
        window.close()
    qml.engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    owner.deleteLater()


def test_two_windows_load_cleanly(running: Running) -> None:
    assert running.warnings == []
    assert running.main.title() == "Recon"
    assert running.panel.title() == "Recon Panel"  # the KWin rule matches this title


def test_main_window_starts_shown_and_panel_hidden(running: Running) -> None:
    assert running.main.isVisible()
    assert not running.panel.isVisible()


def test_main_window_size_fits_the_scaled_desktop(running: Running) -> None:
    assert (running.main.width(), running.main.height()) == (960, 640)
    assert running.main.width() <= 1280
    assert running.main.height() <= 720


def test_panel_width_limits(running: Running) -> None:
    assert running.panel.minimumWidth() == 360
    assert running.panel.maximumWidth() == 520


@pytest.mark.parametrize("running", [480], indirect=True)
def test_panel_opens_at_the_remembered_width(running: Running) -> None:
    running.navigation.showPanel()

    assert wait_until(running.panel.isVisible)
    assert running.panel.width() == 480


def test_resizing_the_panel_is_remembered(running: Running) -> None:
    running.navigation.showPanel()
    wait_until(running.panel.isVisible)

    running.panel.setWidth(470)

    # The resize reaches QML through the platform's event queue, a moment later.
    assert wait_until(lambda: running.settings.property("panelWidth") == 470)
    assert wait_until(lambda: running.saved == [Settings(panel_width=470)])


def test_panel_button_brings_back_a_closed_main_window(running: Running) -> None:
    running.navigation.showPanel()
    wait_until(running.panel.isVisible)
    running.main.close()
    assert wait_until(lambda: not running.main.isVisible())

    QMetaObject.invokeMethod(running.find(running.panel, "openHome"), "clicked")

    assert wait_until(running.main.isVisible)
    assert running.panel.isVisible()


def test_closing_the_main_window_leaves_the_panel_open(running: Running) -> None:
    running.navigation.showPanel()
    wait_until(running.panel.isVisible)

    running.main.close()
    wait(50)

    assert not running.main.isVisible()
    assert running.panel.isVisible()


def test_sidebar_switches_screens(running: Running) -> None:
    loader = running.find(running.main, "screenLoader")
    assert str(loader.property("source").toString()).endswith("screens/Home.qml")

    QMetaObject.invokeMethod(running.find(running.main, "nav-settings"), "clicked")
    wait(50)

    assert running.navigation.property("currentScreen") == "settings"
    assert str(loader.property("source").toString()).endswith("screens/Settings.qml")
    assert running.find(running.main, "nav-settings").property("selected") is True
    assert running.find(running.main, "nav-home").property("selected") is False


def test_both_windows_share_one_navigation_state(running: Running) -> None:
    running.navigation.open("settings")
    wait(20)

    assert running.find(running.main, "nav-settings").property("selected") is True
    assert running.warnings == []
