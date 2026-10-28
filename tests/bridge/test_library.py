"""LibraryBridge: rooms in the vault, History, Open in Obsidian and Restore with Undo."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject

from recon.bridge.library import LibraryBridge, day, history_detail
from recon.db.models import HistoryEntry, Room, Run
from recon.errors import BackupMissingError
from tests.bridge.test_done import Opener
from tests.ui.qml_harness import app

WHEN = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
_OWNERS: list[QObject] = []


@pytest.fixture(autouse=True)
def _delete_on_the_main_thread() -> Iterator[None]:
    yield
    while _OWNERS:
        _OWNERS.pop().deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _room(room_id: int = 3, name: str = "DNS in Detail") -> Room:
    return Room(
        id=room_id, platform="TryHackMe", path="Pre Security", module="Networking", name=name,
        task_count=4, mode="new", status="done", created_at=WHEN, updated_at=WHEN,
        time_spent_s=0, last_task_index=4,
    )  # fmt: skip


def _run(run_id: str, written: int, backed_up: int, restored_from: str | None = None) -> Run:
    return Run(
        id=run_id, room_id=3, status="applied", created_at=WHEN, finished_at=WHEN,
        written=written, backed_up=backed_up, restored_from=restored_from,
    )  # fmt: skip


class Store:
    """Rooms and History, with restores that add an entry."""

    def __init__(self) -> None:
        self.rooms = [_room()]
        self.history = [HistoryEntry(run=_run("r1", 4, 2), room_name="DNS in Detail")]
        self.restored: list[str] = []
        self.error: Exception | None = None

    def load(self) -> tuple[list[Room], list[HistoryEntry]]:
        return list(self.rooms), list(self.history)

    def restore(self, run_id: str) -> Run:
        if self.error is not None:
            raise self.error
        self.restored.append(run_id)
        new = _run(f"undo-{run_id}", 2, 2, restored_from=run_id)
        self.history.insert(0, HistoryEntry(run=new, room_name="DNS in Detail"))
        return new


def _bridge(
    store: Store,
    opener: Opener,
    submit: Callable[[Callable[[], None]], None] = lambda job: job(),
) -> LibraryBridge:
    app()
    owner = QObject()
    _OWNERS.append(owner)
    return LibraryBridge(
        store.load, store.restore, lambda: Path("/vault"), opener.open, submit=submit, parent=owner
    )


def test_wording() -> None:
    assert history_detail(_run("a", 4, 2)) == "4 notes written, 2 replaced"
    assert history_detail(_run("a", 1, 0)) == "1 note written"
    assert history_detail(_run("a", 2, 2, restored_from="r1")) == "Restored 2 notes"
    assert day(WHEN).endswith("October 2026")


def test_refresh_lists_rooms_and_history() -> None:
    library = _bridge(Store(), Opener())

    library.refresh()

    (room,) = library.property("rooms")
    assert (room["id"], room["name"], room["detail"]) == (
        3,
        "DNS in Detail",
        "Pre Security · Networking",
    )
    (entry,) = library.property("history")
    assert entry["runId"] == "r1"
    assert entry["detail"] == "4 notes written, 2 replaced"
    assert entry["canRestore"] is True


def test_open_in_obsidian_opens_the_room_note() -> None:
    opener = Opener()
    library = _bridge(Store(), opener)
    library.refresh()

    library.openRoom(3)
    library.openRoom(99)  # not listed: ignored

    assert opener.opened == [Path("/vault/01 Rooms/TryHackMe/Pre Security/DNS in Detail.md")]
    assert library.property("problem") == ""
    opener.result = False
    library.openRoom(3)
    assert library.property("problem").startswith("Couldn't open DNS in Detail in Obsidian.")


def test_restore_refreshes_and_offers_undo() -> None:
    store = Store()
    library = _bridge(store, Opener())
    library.refresh()
    toasts: list[tuple[str, str]] = []
    library.restored.connect(lambda message, run: toasts.append((message, run)))

    library.restore("r1")
    library.restore("nope")  # not in History: ignored

    assert store.restored == ["r1"]
    assert toasts == [("Restored 2 notes in DNS in Detail to how they were.", "undo-r1")]
    assert [e["runId"] for e in library.property("history")] == ["undo-r1", "r1"]
    assert library.property("history")[0]["detail"] == "Restored 2 notes"


def test_a_missing_backup_is_a_calm_problem(caplog: pytest.LogCaptureFixture) -> None:
    store = Store()
    store.error = BackupMissingError()
    library = _bridge(store, Opener())
    library.refresh()

    library.restore("r1")

    assert library.property("problem") == BackupMissingError.user_message
    store.error = RuntimeError("boom")
    library.restore("r1")
    assert "boom" not in library.property("problem")
    assert "RuntimeError" in caplog.text


def test_one_restore_at_a_time() -> None:
    held: list[Callable[[], None]] = []
    store = Store()
    library = _bridge(store, Opener(), held.append)
    library.refresh()
    held.pop()()

    library.restore("r1")
    library.restore("r1")

    assert len(held) == 1
    assert library.property("busy") is True
    held.pop()()
    assert library.property("busy") is False
