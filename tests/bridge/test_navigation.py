"""NavigationBridge: screen changes and window requests."""

import pytest

from recon.bridge.navigation import MAIN_SCREENS, NavigationBridge
from tests.ui.qml_harness import SignalCounter, app


@pytest.fixture
def navigation() -> NavigationBridge:
    app()
    return NavigationBridge()


def test_starts_on_home(navigation: NavigationBridge) -> None:
    assert navigation.property("currentScreen") == "home" == MAIN_SCREENS[0]


def test_open_changes_screen_and_asks_for_the_main_window(navigation: NavigationBridge) -> None:
    changed = SignalCounter(navigation, "currentScreenChanged()")
    raised = SignalCounter(navigation, "mainWindowRequested()")

    navigation.open("settings")

    assert navigation.property("currentScreen") == "settings"
    assert (changed.count, raised.count) == (1, 1)


def test_opening_the_current_screen_still_raises_the_window(navigation: NavigationBridge) -> None:
    changed = SignalCounter(navigation, "currentScreenChanged()")
    raised = SignalCounter(navigation, "mainWindowRequested()")

    navigation.open("home")

    assert (changed.count, raised.count) == (0, 1)


def test_unknown_screens_are_ignored(navigation: NavigationBridge) -> None:
    raised = SignalCounter(navigation, "mainWindowRequested()")

    navigation.open("nowhere")

    assert navigation.property("currentScreen") == "home"
    assert raised.count == 0


def test_show_panel_asks_for_the_panel(navigation: NavigationBridge) -> None:
    requested = SignalCounter(navigation, "panelRequested()")

    navigation.showPanel()

    assert requested.count == 1


def test_switch_to_changes_screen_without_raising(navigation: NavigationBridge) -> None:
    changed = SignalCounter(navigation, "currentScreenChanged()")
    raised = SignalCounter(navigation, "mainWindowRequested()")

    assert navigation.switch_to("start") is True
    assert navigation.switch_to("start") is True

    assert navigation.property("currentScreen") == "start"
    assert (changed.count, raised.count) == (1, 0)


def test_switch_to_an_unknown_screen_changes_nothing(navigation: NavigationBridge) -> None:
    assert navigation.switch_to("nowhere") is False
    assert navigation.property("currentScreen") == "home"
