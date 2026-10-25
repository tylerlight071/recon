"""SettingsBridge: clamps, notifies, and saves once after changes settle."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QObject

from recon.bridge.settings import SAVE_DELAY_MS, SettingsBridge
from recon.config import Settings
from tests.ui.qml_harness import SignalCounter, app, wait, wait_until


@pytest.fixture
def saved() -> list[Settings]:
    return []


@pytest.fixture
def bridge(saved: list[Settings]) -> Iterator[SettingsBridge]:
    app()
    owner = QObject()
    yield SettingsBridge(Settings(), saved.append, parent=owner)
    owner.deleteLater()


@pytest.mark.parametrize(("asked", "stored"), [(470, 470), (300, 360), (600, 520), (412.6, 413)])
def test_panel_width_is_clamped(bridge: SettingsBridge, asked: float, stored: int) -> None:
    bridge.setProperty("panelWidth", asked)

    assert bridge.property("panelWidth") == stored
    assert bridge.settings.panel_width == stored


def test_change_notifies_once(bridge: SettingsBridge) -> None:
    changed = SignalCounter(bridge, "panelWidthChanged()")

    bridge.setProperty("panelWidth", 480)
    bridge.setProperty("panelWidth", 480)

    assert changed.count == 1


def test_saves_once_after_changes_settle(bridge: SettingsBridge, saved: list[Settings]) -> None:
    for width in (430, 440, 450, 460):
        bridge.setProperty("panelWidth", width)
        wait(20)

    assert saved == []
    assert wait_until(lambda: len(saved) == 1, SAVE_DELAY_MS * 4)
    wait(SAVE_DELAY_MS + 100)
    assert saved == [Settings(panel_width=460)]


def test_flush_saves_now_and_only_when_changed(
    bridge: SettingsBridge, saved: list[Settings]
) -> None:
    bridge.flush()
    assert saved == []

    bridge.setProperty("panelWidth", 500)
    bridge.flush()
    wait(SAVE_DELAY_MS + 100)

    assert saved == [Settings(panel_width=500)]


def test_setting_the_same_width_saves_nothing(
    bridge: SettingsBridge, saved: list[Settings]
) -> None:
    bridge.setProperty("panelWidth", 420)
    wait(SAVE_DELAY_MS + 100)

    assert saved == []


@pytest.mark.parametrize("choice", ["sometimes", "", "ON"])
def test_unknown_pinning_choice_is_ignored(
    bridge: SettingsBridge, saved: list[Settings], choice: str
) -> None:
    bridge.setProperty("pinning", choice)
    wait(SAVE_DELAY_MS + 100)

    assert bridge.property("pinning") == "ask"
    assert saved == []


def test_pinning_choice_is_saved(bridge: SettingsBridge, saved: list[Settings]) -> None:
    bridge.setProperty("pinning", "on")
    bridge.flush()

    assert saved == [Settings(kwin_pinning="on")]


def test_chime_is_off_by_default_and_saved_when_turned_on(
    bridge: SettingsBridge, saved: list[Settings]
) -> None:
    changed = SignalCounter(bridge, "chimeChanged()")
    assert bridge.property("chime") is False

    bridge.setProperty("chime", True)
    bridge.setProperty("chime", True)
    bridge.flush()

    assert bridge.property("chime") is True
    assert changed.count == 1
    assert saved == [Settings(chime=True)]


def test_export_folder_is_remembered(bridge: SettingsBridge, saved: list[Settings]) -> None:
    changed = SignalCounter(bridge, "exportFolderChanged()")

    bridge.setProperty("exportFolder", "/home/tyler/Documents")
    bridge.setProperty("exportFolder", "/home/tyler/Documents")
    bridge.flush()

    assert changed.count == 1
    assert saved == [Settings(export_folder="/home/tyler/Documents")]
