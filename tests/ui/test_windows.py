"""Task 1.3: the panel and main window share one engine and behave as the spec says."""

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QMetaObject, QObject
from PySide6.QtQuick import QQuickItem, QQuickWindow

from recon.app import QmlEngine, create_engine, load_windows, root_window
from recon.bridge.flags import FlagGuard
from recon.bridge.navigation import NavigationBridge
from recon.bridge.pinning import PinningBridge
from recon.bridge.settings import SettingsBridge
from recon.config import Settings
from tests.bridge.test_pinning_bridge import FakePinner
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
    pinner: "FakePinner"
    flag_guard: FlagGuard
    kept: list[tuple[int, str]]

    def find(self, window: QQuickWindow, name: str) -> QObject:
        # Walk the visual tree: Repeater delegates aren't QObject children of the window.
        pending: list[QQuickItem] = [window.contentItem()]
        while pending:
            item = pending.pop()
            if item.objectName() == name:
                return item
            pending.extend(item.childItems())
        raise AssertionError(name)

    def find_object(self, window: QQuickWindow, name: str) -> QObject:
        # Popups (Dialog) live outside the item tree, so search QObject children.
        found = window.findChild(QObject, name)
        assert found is not None, name
        return found


@pytest.fixture
def running(request: pytest.FixtureRequest) -> Iterator[Running]:
    app()
    # Most tests don't want the first-launch pin question in the way.
    initial: Settings = getattr(request, "param", Settings(kwin_pinning="off"))
    owner = QObject()
    saved: list[Settings] = []
    settings = SettingsBridge(initial, saved.append, parent=owner)
    navigation = NavigationBridge(parent=owner)
    pinner = FakePinner()
    pinning = PinningBridge(
        settings, pinner, lambda: (0, 0, 1280, 720), lambda job: job(), parent=owner
    )
    kept: list[tuple[int, str]] = []
    flag_guard = FlagGuard(lambda block, text: kept.append((block, text)) is None, parent=owner)
    qml = create_engine(
        {
            "AppSettings": settings,
            "Navigation": navigation,
            "Pinning": pinning,
            "FlagGuard": flag_guard,
        }
    )
    warnings: list[str] = []
    qml.engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
    assert load_windows(qml.engine)
    main, panel = root_window(qml.engine, 0), root_window(qml.engine, 1)
    assert main is not None
    assert panel is not None
    wait(50)
    yield Running(qml, settings, navigation, main, panel, warnings, saved, pinner, flag_guard, kept)
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


@pytest.mark.parametrize("running", [Settings(panel_width=480, kwin_pinning="off")], indirect=True)
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
    assert wait_until(lambda: running.saved == [Settings(panel_width=470, kwin_pinning="off")])


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


# Task 1.4: the first-launch pin question ------------------------------------------------

ASKING = [Settings(kwin_pinning="ask")]


@pytest.mark.parametrize("running", ASKING, indirect=True)
def test_first_launch_asks_to_pin_the_panel(running: Running) -> None:
    question = running.find_object(running.main, "pinQuestion")

    assert wait_until(lambda: question.property("visible") is True)
    assert question.property("title") == (
        "Pin the Recon panel to the right edge of your screen while you work?"
    )
    assert question.property("primaryText") == "Pin the panel"
    assert running.warnings == []


@pytest.mark.parametrize("running", ASKING, indirect=True)
def test_pin_the_panel_pins_it(running: Running) -> None:
    question = running.find_object(running.main, "pinQuestion")
    wait_until(lambda: question.property("visible") is True)

    QMetaObject.invokeMethod(question, "accept")
    wait(50)

    assert running.settings.property("pinning") == "on"
    assert running.pinner.pinned[0].x == 860


@pytest.mark.parametrize("running", ASKING, indirect=True)
def test_not_now_never_asks_again(running: Running) -> None:
    question = running.find_object(running.main, "pinQuestion")
    wait_until(lambda: question.property("visible") is True)

    QMetaObject.invokeMethod(question, "reject")
    wait(50)

    assert running.settings.property("pinning") == "off"
    assert running.pinner.pinned == []


def test_no_question_once_answered(running: Running) -> None:
    wait(100)

    assert running.find_object(running.main, "pinQuestion").property("visible") is False


@pytest.mark.parametrize("running", [Settings(kwin_pinning="on")], indirect=True)
def test_pin_failure_shows_a_calm_toast(running: Running) -> None:
    running.pinner.method = None
    toast = running.find(running.main, "toast")

    QMetaObject.invokeMethod(
        running.qml.engine.rootContext().contextProperty("Pinning"), "applyIfOn"
    )

    assert wait_until(lambda: toast.property("shown") is True)
    assert toast.property("message").startswith("Couldn't pin the panel.")


# Task 1.6: the "Flag skipped" notice --------------------------------------------------------

MD5 = "5d41402abc4b2a76b9719d911017c592"


def test_braced_flag_notice_has_no_keep_button(running: Running) -> None:
    toast = running.find(running.panel, "flagToast")

    running.flag_guard.clean(7, "answer THM{x}", [])

    assert wait_until(lambda: toast.property("shown") is True)
    assert toast.property("message") == "Flag skipped. Recon never saves flags."
    assert toast.property("actionText") == ""


def test_hash_notice_offers_not_a_flag_keep_it(running: Running) -> None:
    toast = running.find(running.panel, "flagToast")
    restored: list[tuple[int, str]] = []
    running.flag_guard.keptRestored.connect(lambda block, text: restored.append((block, text)))

    running.flag_guard.clean(7, f"md5 {MD5}", [])
    assert wait_until(lambda: toast.property("shown") is True)
    assert toast.property("actionText") == "Not a flag, keep it"

    QMetaObject.invokeMethod(running.find(running.panel, "action"), "clicked")
    wait(20)

    assert running.kept == [(7, MD5)]
    assert restored == [(7, MD5)]
    assert toast.property("shown") is False
