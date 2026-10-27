"""FinishBridge: mark done, export, go back, close; and its plain wording."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from PySide6.QtCore import QUrl

from recon.bridge.finish import FinishBridge, shown_path, summary
from recon.bridge.settings import SettingsBridge
from recon.config import Settings
from recon.db.connection import Database
from recon.db.migrate import migrate
from recon.db.models import BlockContent, NewRoom, Task
from recon.db.repositories import BlockRepository, RoomRepository, TaskRepository, UndoRepository
from recon.errors import ExportFolderMissingError, ReconError
from tests.ui.qml_harness import SignalCounter, app


def _task(index: int, status: str) -> Task:
    return Task.model_validate(
        {"id": index, "room_id": 1, "task_index": index, "title": "", "status": status}
    )


@pytest.mark.parametrize(
    ("statuses", "words"),
    [
        (["done"], "1 task written up."),
        (["done", "done", "done"], "All 3 tasks written up."),
        (["done", "skipped", "done"], "3 tasks: 2 written up, 1 skipped."),
        (["skipped"], "1 task: 0 written up, 1 skipped."),
    ],
)
def test_summary(statuses: list[str], words: str) -> None:
    assert summary([_task(i + 1, s) for i, s in enumerate(statuses)]) == words


def test_shown_path() -> None:
    home = Path("/home/tyler")

    assert shown_path(home / "Documents" / "Recon", home) == "~/Documents/Recon"
    assert shown_path(Path("/data/exports"), home) == "/data/exports"


@dataclass
class Setup:
    finish: FinishBridge
    rooms: RoomRepository
    tasks: TaskRepository
    blocks: BlockRepository
    settings: SettingsBridge
    opened: list[Path]
    home: Path
    room_id: int


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    folder = tmp_path / "recon"
    folder.mkdir(mode=0o700)
    database = Database.open(folder / "app.db")
    migrate(database)
    yield database
    database.close()


@pytest.fixture
def setup(db: Database, tmp_path: Path) -> Setup:
    app()
    rooms, tasks, blocks = RoomRepository(db), TaskRepository(db), BlockRepository(db)
    room = rooms.create(NewRoom(name="DNS in Detail", task_count=2, path="Pre Security"))
    first, second = tasks.for_room(room.id)
    blocks.add(first.id, "key_idea", BlockContent(text="TXT records hold text"))
    tasks.set_status(first.id, "done")
    tasks.set_status(second.id, "skipped")
    tasks.add_time(first.id, 4320)
    settings = SettingsBridge(Settings(), lambda _s: None)
    opened: list[Path] = []
    home = tmp_path / "home"
    (home / "Documents").mkdir(parents=True)
    finish = FinishBridge(
        (rooms, tasks, blocks, UndoRepository(db)),
        settings,
        lambda folder: opened.append(folder) is None,
        submit=lambda job: job(),
        today=lambda: date(2026, 10, 25),
        home=home,
    )
    return Setup(finish, rooms, tasks, blocks, settings, opened, home, room.id)


def test_hidden_until_a_room_finishes(setup: Setup) -> None:
    finish = setup.finish

    assert finish.property("shown") is False
    assert (finish.property("roomName"), finish.property("summary")) == ("", "")
    assert (finish.property("timeSpent"), finish.property("exportedText")) == ("", "")
    assert finish.property("folderUrl") == ""


def test_open_marks_the_room_done_and_shows_what_was_done(setup: Setup) -> None:
    setup.finish.open(setup.room_id)

    room = setup.rooms.get(setup.room_id)
    assert room is not None
    assert room.status == "done"
    finish = setup.finish
    assert finish.property("shown") is True
    assert finish.property("roomName") == "DNS in Detail"
    assert finish.property("summary") == "2 tasks: 1 written up, 1 skipped."
    assert finish.property("timeSpent") == "1 hour 12 minutes"
    assert finish.property("busy") is False


def test_export_writes_the_note_and_remembers_the_folder(setup: Setup) -> None:
    folder = setup.home / "Documents"
    setup.finish.open(setup.room_id)

    setup.finish.export(QUrl.fromLocalFile(str(folder)).toString())

    note = folder / "DNS in Detail.md"
    text = note.read_text(encoding="utf-8")
    assert text.startswith("# DNS in Detail\n\nTryHackMe · Pre Security\n")
    assert "TXT records hold text" in text
    assert "*Skipped.*" in text
    assert setup.finish.property("exportedText") == "Saved as DNS in Detail.md in ~/Documents"
    assert setup.settings.property("exportFolder") == str(folder)
    assert setup.finish.property("folderUrl") == QUrl.fromLocalFile(str(folder)).toString()

    setup.finish.openFolder()
    assert setup.opened == [folder.resolve()]


def test_export_problems_are_told_calmly(setup: Setup) -> None:
    failures: list[str] = []
    setup.finish.failed.connect(failures.append)
    setup.finish.open(setup.room_id)

    setup.finish.export(QUrl.fromLocalFile(str(setup.home / "gone")).toString())

    assert failures == [ExportFolderMissingError.user_message]
    assert setup.finish.property("busy") is False
    assert setup.finish.property("exportedText") == ""


def test_export_without_a_room_or_folder_does_nothing(setup: Setup) -> None:
    setup.finish.export(QUrl.fromLocalFile(str(setup.home)).toString())
    setup.finish.open(setup.room_id)
    setup.finish.export("")
    setup.finish.openFolder()

    assert list((setup.home / "Documents").iterdir()) == []
    assert setup.opened == []


def test_back_to_the_room_undoes_the_finish(setup: Setup) -> None:
    reopened: list[int] = []
    setup.finish.reopenRequested.connect(reopened.append)
    setup.finish.open(setup.room_id)

    setup.finish.backToRoom()

    room = setup.rooms.get(setup.room_id)
    assert room is not None
    assert room.status == "capturing"
    assert reopened == [setup.room_id]
    assert setup.finish.property("shown") is False
    setup.finish.backToRoom()  # nothing open now
    assert reopened == [setup.room_id]


def test_done_closes(setup: Setup) -> None:
    closed = SignalCounter(setup.finish, "closed()")
    setup.finish.open(setup.room_id)

    setup.finish.close()

    assert closed.count == 1
    assert setup.finish.property("shown") is False


class SurprisingRooms(RoomRepository):
    def update_progress(self, *_args: object, **_kwargs: object) -> bool:
        raise RuntimeError


def test_an_unexpected_failure_never_leaves_finish_stuck(db: Database, setup: Setup) -> None:
    finish = FinishBridge(
        (SurprisingRooms(db), setup.tasks, setup.blocks, UndoRepository(db)),
        setup.settings,
        lambda _folder: True,
        submit=lambda job: job(),
    )
    failures: list[str] = []
    finish.failed.connect(failures.append)

    finish.open(setup.room_id)

    assert failures == [ReconError.user_message]
    assert finish.property("busy") is False
