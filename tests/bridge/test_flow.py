"""The room flow: Home opens Start, a new room or "Carry on" opens the panel."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from recon.bridge.flow import connect_room_flow
from recon.bridge.home import HomeBridge
from recon.bridge.navigation import NavigationBridge
from recon.bridge.start import StartRoomBridge
from recon.db.connection import Database
from recon.db.migrate import migrate
from recon.db.repositories import BlockRepository, RoomRepository, utc_now
from tests.ui.qml_harness import SignalCounter, app


@pytest.fixture
def flow(tmp_path: Path) -> Iterator[tuple[NavigationBridge, HomeBridge, StartRoomBridge]]:
    app()
    folder = tmp_path / "recon"
    folder.mkdir(mode=0o700)
    db = Database.open(folder / "app.db")
    migrate(db)
    rooms = RoomRepository(db)
    navigation = NavigationBridge()
    home = HomeBridge(rooms, BlockRepository(db), utc_now)
    start = StartRoomBridge(rooms, lambda job: job())
    connect_room_flow(navigation, home, start)
    yield navigation, home, start
    db.close()


def test_start_a_room_opens_start(
    flow: tuple[NavigationBridge, HomeBridge, StartRoomBridge],
) -> None:
    navigation, home, _start = flow

    home.primary()

    assert navigation.property("currentScreen") == "start"


def test_a_new_room_opens_the_panel_and_home_waits_behind(
    flow: tuple[NavigationBridge, HomeBridge, StartRoomBridge],
) -> None:
    navigation, _home, start = flow
    navigation.open("start")
    panel = SignalCounter(navigation, "panelRequested()")
    raised = SignalCounter(navigation, "mainWindowRequested()")

    start.start("DNS in Detail", "7", "", "")

    assert navigation.property("currentScreen") == "home"
    assert (panel.count, raised.count) == (1, 0)


def test_carry_on_opens_the_panel(
    flow: tuple[NavigationBridge, HomeBridge, StartRoomBridge],
) -> None:
    navigation, home, start = flow
    start.start("DNS in Detail", "7", "", "")
    home.refresh()
    panel = SignalCounter(navigation, "panelRequested()")

    home.primary()

    assert panel.count == 1
