"""HomeBridge: the primary action, "Where was I?", recent rooms, and calm time words."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from recon.bridge.home import HomeBridge, ago, last_line
from recon.db.connection import Database
from recon.db.migrate import migrate
from recon.db.models import BlockContent, NewRoom
from recon.db.repositories import BlockRepository, RoomRepository, TaskRepository
from tests.db.conftest import FakeClock
from tests.ui.qml_harness import SignalCounter, app

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("delta", "words"),
    [
        (timedelta(seconds=0), "just now"),
        (timedelta(seconds=59), "just now"),
        (timedelta(minutes=1), "1 minute ago"),
        (timedelta(minutes=59), "59 minutes ago"),
        (timedelta(hours=1), "1 hour ago"),
        (timedelta(hours=23), "23 hours ago"),
        (timedelta(days=1), "yesterday"),
        (timedelta(days=2), "2 days ago"),
        (timedelta(days=13), "13 days ago"),
        (timedelta(days=14), "2 weeks ago"),
        (timedelta(days=59), "8 weeks ago"),
        (timedelta(days=60), "on 26 August 2026"),
        (timedelta(seconds=-30), "just now"),  # clock skew never shows the future
    ],
)
def test_ago_words(delta: timedelta, words: str) -> None:
    assert ago(NOW - delta, NOW) == words


@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("TXT records hold text", "TXT records hold text"),
        ("first\nsecond\n\n  ", "second"),
        ("   padded   ", "padded"),
        ("", ""),
        ("\n\n", ""),
        ("x" * 80, "x" * 80),
        ("x" * 81, "x" * 79 + "\N{HORIZONTAL ELLIPSIS}"),
    ],
)
def test_last_line(text: str, line: str) -> None:
    assert last_line(text) == line


@pytest.fixture
def clock() -> FakeClock:
    clock = FakeClock()
    clock.now = NOW - timedelta(days=3)
    return clock


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    folder = tmp_path / "recon"
    folder.mkdir(mode=0o700)
    database = Database.open(folder / "app.db")
    migrate(database)
    yield database
    database.close()


@pytest.fixture
def repos(db: Database, clock: FakeClock) -> tuple[RoomRepository, TaskRepository, BlockRepository]:
    return RoomRepository(db, clock), TaskRepository(db, clock), BlockRepository(db, clock)


def _home(repos: tuple[RoomRepository, TaskRepository, BlockRepository]) -> HomeBridge:
    app()
    rooms, _tasks, blocks = repos
    return HomeBridge(rooms, blocks, lambda: NOW)


def test_first_launch_offers_start_a_room(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository],
) -> None:
    home = _home(repos)
    started = SignalCounter(home, "startRequested()")

    assert home.property("hasCurrent") is False
    assert home.property("primaryText") == "Start a room"
    assert home.property("recentRooms") == []

    home.primary()

    assert started.count == 1


def test_where_was_i(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository], clock: FakeClock
) -> None:
    rooms, tasks, blocks = repos
    room = rooms.create(NewRoom(name="DNS in Detail", task_count=7))
    task = tasks.for_room(room.id)[3]
    blocks.add(task.id, "key_idea", BlockContent(text="A records point at IPv4"))
    clock.advance(60)
    blocks.add(task.id, "key_idea", BlockContent(text="MX is mail\nTXT records hold text"))
    clock.advance(60)
    blocks.add(task.id, "key_idea")  # an empty block doesn't count as the last note
    rooms.update_progress(room.id, last_task_index=4)

    home = _home(repos)
    resumed: list[int] = []
    home.resumeRequested.connect(resumed.append)

    assert home.property("hasCurrent") is True
    assert home.property("primaryText") == "Carry on with DNS in Detail"
    assert home.property("currentName") == "DNS in Detail"
    assert home.property("currentTask") == "Task 4 of 7"
    assert home.property("currentWhen") == "2 days ago"
    assert home.property("lastNote") == "TXT records hold text"

    home.primary()
    assert resumed == [room.id]


def test_finished_rooms_are_listed_not_resumed(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository], clock: FakeClock
) -> None:
    rooms, _tasks, _blocks = repos
    done = rooms.create(
        NewRoom(name="Linux Basics", task_count=4, path="Pre Security", module="Linux")
    )
    rooms.update_progress(done.id, status="done")
    clock.advance(3600)
    waiting = rooms.create(NewRoom(name="Intro to Networking", task_count=4))
    rooms.update_progress(waiting.id, status="in_review")

    home = _home(repos)
    resumed = SignalCounter(home, "resumeRequested(int)")

    assert home.property("hasCurrent") is False
    rows = home.property("recentRooms")
    assert [(r["name"], r["detail"], r["canResume"]) for r in rows] == [
        ("Intro to Networking", "Ready to review", False),
        ("Linux Basics", "Pre Security · Linux · Done", False),
    ]
    finished: list[int] = []
    reviewing: list[int] = []
    home.finishedRequested.connect(finished.append)
    home.reviewRequested.connect(reviewing.append)
    home.resume(done.id)
    home.resume(waiting.id)
    home.resume(9999)
    assert resumed.count == 0
    assert finished == [done.id]  # a finished room opens its Finish screen (audit F-11)
    assert reviewing == [waiting.id]  # one ready to review opens the review
    assert [r["canOpen"] for r in home.property("recentRooms")] == [True, True]


def test_recent_rooms_exclude_the_current_one_and_stop_at_five(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository], clock: FakeClock
) -> None:
    rooms, _tasks, _blocks = repos
    for n in range(7):
        rooms.create(NewRoom(name=f"Room {n}", task_count=2, path="Path"))
        clock.advance(60)

    home = _home(repos)

    assert home.property("currentName") == "Room 6"
    names = [r["name"] for r in home.property("recentRooms")]
    assert names == ["Room 5", "Room 4", "Room 3", "Room 2", "Room 1"]
    first = home.property("recentRooms")[0]
    assert (first["detail"], first["canResume"]) == ("Path · Task 1 of 2", True)


def test_resume_a_recent_room_still_being_captured(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository], clock: FakeClock
) -> None:
    rooms, _tasks, _blocks = repos
    older = rooms.create(NewRoom(name="Older", task_count=1))
    clock.advance(60)
    rooms.create(NewRoom(name="Newer", task_count=1))
    home = _home(repos)
    resumed: list[int] = []
    home.resumeRequested.connect(resumed.append)

    home.resume(older.id)

    assert resumed == [older.id]


def test_start_new_while_a_room_is_open(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository],
) -> None:
    repos[0].create(NewRoom(name="R", task_count=1))
    home = _home(repos)
    started = SignalCounter(home, "startRequested()")

    home.startNew()

    assert started.count == 1


def test_refresh_picks_up_new_rooms(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository],
) -> None:
    home = _home(repos)
    changed = SignalCounter(home, "changed()")
    repos[0].create(NewRoom(name="New", task_count=1))

    home.refresh()

    assert changed.count == 1
    assert home.property("currentName") == "New"
