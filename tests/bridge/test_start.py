"""StartRoomBridge: two fields checked calmly, the room saved off the UI thread."""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from recon.bridge.start import (
    MAX_TASKS,
    NAME_LIMIT,
    NEED_NAME,
    NEED_TASKS,
    PLACE_LIMIT,
    StartRoomBridge,
    parse_task_count,
)
from recon.bridge.workers import thread_pool_submit
from recon.db.connection import Database
from recon.db.migrate import migrate
from recon.db.models import NewRoom, Room
from recon.db.repositories import RoomRepository
from recon.errors import ReconError, StorageError
from tests.db.conftest import FakeClock
from tests.ui.qml_harness import SignalCounter, app, wait_until


@pytest.mark.parametrize(
    ("text", "count"),
    [
        ("7", 7),
        (" 12 ", 12),
        ("1", 1),
        (str(MAX_TASKS), MAX_TASKS),
        ("07", 7),
        ("0", None),
        (str(MAX_TASKS + 1), None),
        ("", None),
        ("seven", None),
        ("-3", None),
        ("2.5", None),
        ("\N{ARABIC-INDIC DIGIT SEVEN}", None),  # only plain digits count
    ],
)
def test_parse_task_count(text: str, count: int | None) -> None:
    assert parse_task_count(text) == count


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    folder = tmp_path / "recon"
    folder.mkdir(mode=0o700)
    database = Database.open(folder / "app.db")
    migrate(database)
    yield database
    database.close()


@pytest.fixture
def rooms(db: Database) -> RoomRepository:
    return RoomRepository(db, FakeClock())


class Held:
    """A submit that keeps jobs until told to run them (to see the busy state)."""

    def __init__(self) -> None:
        self.jobs: list[Callable[[], None]] = []

    def __call__(self, job: Callable[[], None]) -> None:
        self.jobs.append(job)

    def run(self) -> None:
        for job in self.jobs:
            job()


class BrokenRooms(RoomRepository):
    """Rooms whose writes fail, as on a full disk."""

    def create(self, _new: NewRoom) -> Room:
        raise StorageError


class SurprisingRooms(RoomRepository):
    """Rooms whose writes fail in a way nobody planned for."""

    def create(self, _new: NewRoom) -> Room:
        raise RuntimeError


def _bridge(rooms: RoomRepository) -> tuple[StartRoomBridge, list[int]]:
    app()
    bridge = StartRoomBridge(rooms, lambda job: job())
    started: list[int] = []
    bridge.started.connect(started.append)
    return bridge, started


def test_nothing_remembered_on_the_first_room(rooms: RoomRepository) -> None:
    bridge, _started = _bridge(rooms)

    assert (bridge.property("lastPath"), bridge.property("lastModule")) == ("", "")
    assert bridge.property("problem") == ""
    assert bridge.property("busy") is False
    assert bridge.property("maxTasks") == MAX_TASKS
    assert bridge.property("nameLimit") == NAME_LIMIT
    assert bridge.property("placeLimit") == PLACE_LIMIT


def test_path_and_module_come_from_the_last_room(rooms: RoomRepository) -> None:
    rooms.create(NewRoom(name="Old", task_count=1, path="Pre Security", module="Linux"))
    bridge, _started = _bridge(rooms)

    assert (bridge.property("lastPath"), bridge.property("lastModule")) == (
        "Pre Security",
        "Linux",
    )


def test_start_creates_the_room_and_reports_it(rooms: RoomRepository) -> None:
    bridge, started = _bridge(rooms)

    bridge.start("  DNS in Detail ", " 7", " Pre Security ", "Networking ")

    room = rooms.current()
    assert room is not None
    assert started == [room.id]
    assert (room.name, room.task_count, room.path, room.module, room.mode) == (
        "DNS in Detail",
        7,
        "Pre Security",
        "Networking",
        "new",
    )
    assert bridge.property("problem") == ""
    assert bridge.property("busy") is False


@pytest.mark.parametrize(
    ("name", "tasks", "problem"),
    [
        ("", "7", NEED_NAME),
        ("   ", "7", NEED_NAME),
        ("", "", NEED_NAME),  # one thing at a time: the name first
        ("DNS", "", NEED_TASKS),
        ("DNS", "0", NEED_TASKS),
        ("DNS", "lots", NEED_TASKS),
    ],
)
def test_missing_fields_are_asked_for_calmly(
    rooms: RoomRepository, name: str, tasks: str, problem: str
) -> None:
    bridge, started = _bridge(rooms)

    bridge.start(name, tasks, "", "")

    assert bridge.property("problem") == problem
    assert started == []
    assert rooms.recent() == []


def test_the_message_clears_once_fixed(rooms: RoomRepository) -> None:
    bridge, _started = _bridge(rooms)
    bridge.start("", "7", "", "")

    bridge.start("DNS", "7", "", "")

    assert bridge.property("problem") == ""


def test_refresh_clears_an_old_message(rooms: RoomRepository) -> None:
    bridge, _started = _bridge(rooms)
    bridge.start("", "7", "", "")
    changed = SignalCounter(bridge, "changed()")

    bridge.refresh()

    assert bridge.property("problem") == ""
    assert changed.count == 1


def test_long_fields_are_cut_to_their_limits(rooms: RoomRepository) -> None:
    bridge, _started = _bridge(rooms)

    bridge.start("n" * (NAME_LIMIT + 10), "1", "p" * (PLACE_LIMIT + 1), "m" * (PLACE_LIMIT + 1))

    room = rooms.current()
    assert room is not None
    assert (len(room.name), len(room.path), len(room.module)) == (
        NAME_LIMIT,
        PLACE_LIMIT,
        PLACE_LIMIT,
    )


def test_a_flag_in_the_name_is_never_stored(rooms: RoomRepository) -> None:
    bridge, _started = _bridge(rooms)

    bridge.start("Crack THM{s3cret} room", "2", "", "")

    room = rooms.current()
    assert room is not None
    assert "THM{" not in room.name


def test_busy_while_saving_and_a_second_press_is_ignored(rooms: RoomRepository) -> None:
    app()
    held = Held()
    bridge = StartRoomBridge(rooms, held)
    started: list[int] = []
    bridge.started.connect(started.append)

    bridge.start("DNS", "3", "", "")
    bridge.start("DNS", "3", "", "")

    assert bridge.property("busy") is True
    assert len(held.jobs) == 1
    held.run()
    assert bridge.property("busy") is False
    assert len(started) == 1
    assert len(rooms.recent()) == 1


def test_a_failed_save_says_what_to_do(db: Database) -> None:
    bridge, started = _bridge(BrokenRooms(db, FakeClock()))

    bridge.start("DNS", "3", "", "")

    assert bridge.property("problem") == StorageError.user_message
    assert bridge.property("busy") is False
    assert started == []


def test_the_room_is_saved_off_the_ui_thread(rooms: RoomRepository) -> None:
    app()
    bridge = StartRoomBridge(rooms, thread_pool_submit)
    started: list[int] = []
    bridge.started.connect(started.append)

    bridge.start("DNS", "3", "", "")

    assert wait_until(lambda: started != [])
    assert bridge.property("busy") is False


def test_an_unexpected_failure_never_leaves_start_stuck(db: Database) -> None:
    bridge, started = _bridge(SurprisingRooms(db, FakeClock()))

    bridge.start("DNS", "3", "", "")

    assert bridge.property("problem") == ReconError.user_message
    assert bridge.property("busy") is False
    assert started == []
