"""DoneBridge: the finished room, its place in its path, and Open in Obsidian."""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject

from recon.bridge.done import DoneBridge, progress_line
from recon.db.connection import Database
from recon.db.migrate import migrate
from recon.db.models import NewRoom
from recon.db.repositories import RoomRepository
from recon.errors import StorageError
from tests.ui.qml_harness import SignalCounter, app

_OWNERS: list[QObject] = []


@pytest.fixture(autouse=True)
def _delete_on_the_main_thread() -> Iterator[None]:
    yield
    while _OWNERS:
        _OWNERS.pop().deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def rooms(tmp_path: Path) -> Iterator[RoomRepository]:
    db = Database.open(tmp_path / "app.db")
    migrate(db)
    yield RoomRepository(db)
    db.close()


class Opener:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.opened: list[Path] = []
        self.forgotten = 0

    def open(self, note: Path) -> bool:
        self.opened.append(note)
        return self.result

    def forget(self) -> None:
        self.forgotten += 1


def _bridge(rooms: RoomRepository, opener: Opener, vault: Path) -> DoneBridge:
    app()
    owner = QObject()
    _OWNERS.append(owner)
    submit: Callable[[Callable[[], None]], None] = lambda job: job()  # noqa: E731
    return DoneBridge(rooms, lambda: vault, opener.open, opener.forget, submit=submit, parent=owner)


def _done_room(rooms: RoomRepository, name: str, path: str = "Pre Security") -> int:
    room = rooms.create(NewRoom(name=name, task_count=1, path=path))
    rooms.update_progress(room.id, status="done")
    return room.id


@pytest.mark.parametrize(
    ("done", "path", "line"),
    [
        (1, "Pre Security", "Your first room in Pre Security."),
        (3, "Pre Security", "3 rooms done in Pre Security."),
        (1, "", "1 room done so far."),
        (4, "", "4 rooms done so far."),
    ],
)
def test_progress_is_only_ever_what_is_done(done: int, path: str, line: str) -> None:
    assert progress_line(done, path) == line


def test_showing_a_room_says_where_it_stands(rooms: RoomRepository, tmp_path: Path) -> None:
    _done_room(rooms, "Linux Basics")
    room = _done_room(rooms, "DNS in Detail")
    _done_room(rooms, "Elsewhere", path="Other path")
    done = _bridge(rooms, Opener(), tmp_path / "vault")
    opened = SignalCounter(done, "opened()")

    done.show(room, written=12)

    assert opened.count == 1
    assert done.property("roomName") == "DNS in Detail"
    assert done.property("written") == 12
    assert done.property("progress") == "2 rooms done in Pre Security."


def test_open_in_obsidian_opens_the_room_note(rooms: RoomRepository, tmp_path: Path) -> None:
    opener = Opener()
    done = _bridge(rooms, opener, tmp_path / "vault")
    done.openInObsidian()  # nothing shown yet: nothing to open
    assert opener.opened == []
    done.show(_done_room(rooms, "DNS in Detail"))

    done.openInObsidian()

    assert opener.opened == [
        tmp_path / "vault" / "01 Rooms" / "TryHackMe" / "Pre Security" / "DNS in Detail.md"
    ]
    assert done.property("tried") is True
    assert done.property("problem") == ""


def test_a_link_that_fails_says_so_calmly(rooms: RoomRepository, tmp_path: Path) -> None:
    opener = Opener(result=False)
    done = _bridge(rooms, opener, tmp_path)
    done.show(_done_room(rooms, "DNS in Detail"))

    done.openInObsidian()

    assert done.property("problem").startswith("Couldn't open Obsidian.")


def test_didnt_open_brings_back_the_one_time_step(rooms: RoomRepository, tmp_path: Path) -> None:
    opener = Opener()
    done = _bridge(rooms, opener, tmp_path)
    done.show(_done_room(rooms, "DNS in Detail"))
    done.openInObsidian()

    done.notOpened()

    assert opener.forgotten == 1
    assert done.property("tried") is False


def test_a_missing_room_or_failed_read_shows_nothing(
    rooms: RoomRepository, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = _bridge(rooms, Opener(), tmp_path)
    opened = SignalCounter(done, "opened()")

    done.show(9999)

    def broken(_self: RoomRepository, _path: str) -> int:
        raise StorageError

    room = _done_room(rooms, "DNS in Detail")
    monkeypatch.setattr(RoomRepository, "done_in_path", broken)
    done.show(room)

    assert opened.count == 0
