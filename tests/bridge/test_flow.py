"""The room flow: Home opens Start, a new room or "Carry on" opens the panel."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from recon.bridge.flags import FlagGuard
from recon.bridge.flow import connect_room_flow
from recon.bridge.home import HomeBridge
from recon.bridge.navigation import NavigationBridge
from recon.bridge.session import RoomSessionBridge
from recon.bridge.start import StartRoomBridge
from recon.db.connection import Database
from recon.db.migrate import migrate
from recon.db.repositories import BlockRepository, RoomRepository, TaskRepository, utc_now
from tests.bridge.fakes import FakeAutosave
from tests.ui.qml_harness import SignalCounter, app

type Flow = tuple[NavigationBridge, HomeBridge, StartRoomBridge, RoomSessionBridge]


@pytest.fixture
def flow(tmp_path: Path) -> Iterator[Flow]:
    app()
    folder = tmp_path / "recon"
    folder.mkdir(mode=0o700)
    db = Database.open(folder / "app.db")
    migrate(db)
    rooms = RoomRepository(db)
    navigation = NavigationBridge()
    blocks = BlockRepository(db)
    home = HomeBridge(rooms, blocks, utc_now)
    start = StartRoomBridge(rooms, lambda job: job())
    session = RoomSessionBridge(
        (rooms, TaskRepository(db), blocks),
        FakeAutosave(blocks),
        FlagGuard(blocks.keep_lookalike),
        submit=lambda job: job(),
    )
    connect_room_flow(navigation, home, start, session)
    yield navigation, home, start, session
    db.close()


def test_start_a_room_opens_start(
    flow: Flow,
) -> None:
    navigation, home, _start, _session = flow

    home.primary()

    assert navigation.property("currentScreen") == "start"


def test_a_new_room_opens_the_panel_and_home_waits_behind(
    flow: Flow,
) -> None:
    navigation, _home, start, session = flow
    navigation.open("start")
    panel = SignalCounter(navigation, "panelRequested()")
    raised = SignalCounter(navigation, "mainWindowRequested()")

    start.start("DNS in Detail", "7", "", "")

    assert navigation.property("currentScreen") == "home"
    assert (panel.count, raised.count) == (1, 0)
    assert session.property("roomName") == "DNS in Detail"


def test_carry_on_opens_the_panel(
    flow: Flow,
) -> None:
    navigation, home, start, session = flow
    start.start("DNS in Detail", "7", "", "")
    home.refresh()
    panel = SignalCounter(navigation, "panelRequested()")

    changed = SignalCounter(home, "changed()")

    home.primary()

    assert panel.count == 1
    assert session.property("taskLabel") == "Task 1 of 7"
    assert changed.count >= 1  # Home follows the session
