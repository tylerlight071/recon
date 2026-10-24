"""PinningBridge: asks once, pins off the UI thread, re-pins on width changes, reports failures."""

from collections.abc import Callable, Iterator

import pytest
from PySide6.QtCore import QObject

from recon.bridge.pinning import REAPPLY_DELAY_MS, PinningBridge, thread_pool_submit
from recon.bridge.settings import SettingsBridge
from recon.config import PinningChoice, Settings
from recon.services.kwin import Method, PanelGeometry
from tests.ui.qml_harness import SignalCounter, app, wait, wait_until

AREA = (0, 0, 1280, 720)


class FakePinner:
    def __init__(self) -> None:
        self.pinned: list[PanelGeometry] = []
        self.unpinned = 0
        self.method: Method | None = Method.RULE
        self.unpin_works = True

    def pin(self, geometry: PanelGeometry) -> Method | None:
        self.pinned.append(geometry)
        return self.method

    def unpin(self) -> bool:
        self.unpinned += 1
        return self.unpin_works


def _now(job: Callable[[], None]) -> None:
    job()


@pytest.fixture
def owner() -> Iterator[QObject]:
    app()
    parent = QObject()
    yield parent
    parent.deleteLater()


def _bridge(
    owner: QObject,
    choice: PinningChoice = "ask",
    *,
    submit: Callable[[Callable[[], None]], None] = _now,
) -> tuple[PinningBridge, SettingsBridge, FakePinner]:
    settings = SettingsBridge(Settings(kwin_pinning=choice), lambda _s: None, parent=owner)
    pinner = FakePinner()
    return PinningBridge(settings, pinner, lambda: AREA, submit, parent=owner), settings, pinner


def test_asks_on_first_launch_only(owner: QObject) -> None:
    bridge, _settings, _pinner = _bridge(owner)
    assert bridge.property("askNeeded") is True

    for choice in ("on", "off"):
        other, _s, _p = _bridge(owner, choice)
        assert other.property("askNeeded") is False


def test_yes_pins_at_the_right_edge_with_the_settings_width(owner: QObject) -> None:
    bridge, settings, pinner = _bridge(owner)
    changed = SignalCounter(bridge, "askNeededChanged()")

    bridge.pin()

    assert settings.property("pinning") == "on"
    assert pinner.pinned == [PanelGeometry(x=860, y=0, width=420)]
    assert bridge.last_method is Method.RULE
    assert changed.count == 1
    assert bridge.property("askNeeded") is False


def test_not_now_turns_it_off_without_touching_kde(owner: QObject) -> None:
    bridge, settings, pinner = _bridge(owner)

    bridge.decline()

    assert settings.property("pinning") == "off"
    assert (pinner.pinned, pinner.unpinned) == ([], 0)


def test_failure_is_reported(owner: QObject) -> None:
    bridge, _settings, pinner = _bridge(owner)
    pinner.method = None
    failed = SignalCounter(bridge, "pinFailed()")

    bridge.pin()

    assert failed.count == 1
    assert bridge.last_method is None


@pytest.mark.parametrize("choice", ["ask", "off"])
def test_apply_does_nothing_unless_on(owner: QObject, choice: PinningChoice) -> None:
    bridge, _settings, pinner = _bridge(owner, choice)

    bridge.applyIfOn()

    assert pinner.pinned == []


def test_width_change_while_pinned_rewrites_the_rule_once(owner: QObject) -> None:
    bridge, settings, pinner = _bridge(owner, "on")

    for width in (440, 460, 480):
        settings.setProperty("panelWidth", width)

    assert pinner.pinned == []
    assert wait_until(lambda: len(pinner.pinned) == 1, REAPPLY_DELAY_MS * 4)
    wait(REAPPLY_DELAY_MS + 100)
    assert pinner.pinned == [PanelGeometry(x=800, y=0, width=480)]
    assert bridge.last_method is Method.RULE


def test_width_change_while_unpinned_touches_nothing(owner: QObject) -> None:
    _bridge_obj, settings, pinner = _bridge(owner, "off")

    settings.setProperty("panelWidth", 480)
    wait(REAPPLY_DELAY_MS + 100)

    assert pinner.pinned == []


def test_unpin_turns_off_and_removes_the_rule(owner: QObject) -> None:
    bridge, settings, pinner = _bridge(owner, "on")
    failed = SignalCounter(bridge, "unpinFailed()")

    bridge.unpin()

    assert settings.property("pinning") == "off"
    assert pinner.unpinned == 1
    assert failed.count == 0


def test_unpin_failure_is_reported(owner: QObject) -> None:
    bridge, _settings, pinner = _bridge(owner, "on")
    pinner.unpin_works = False
    failed = SignalCounter(bridge, "unpinFailed()")

    bridge.unpin()

    assert wait_until(lambda: failed.count == 1)


def test_real_thread_pool_delivers_the_result_back(owner: QObject) -> None:
    bridge, _settings, pinner = _bridge(owner, "on", submit=thread_pool_submit)
    pinner.method = None
    failed = SignalCounter(bridge, "pinFailed()")

    bridge.applyIfOn()

    assert wait_until(lambda: failed.count == 1)
    assert len(pinner.pinned) == 1
