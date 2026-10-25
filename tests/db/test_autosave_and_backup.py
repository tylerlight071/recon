"""Autosave timing and the daily snapshot."""

import sqlite3
import stat
import threading
import time
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest

from recon.db import backup
from recon.db.autosave import AutosaveQueue
from recon.db.connection import Database
from recon.db.models import BlockContent, NewRoom
from recon.db.repositories import BlockRepository, RoomRepository, TaskRepository
from recon.errors import StorageError


class Recorder:
    def __init__(self) -> None:
        self.saved: list[tuple[int, str, float]] = []
        self.fail_next = 0
        self.lock = threading.Lock()

    def __call__(self, block_id: int, content: BlockContent) -> bool:
        with self.lock:
            if self.fail_next:
                self.fail_next -= 1
                raise StorageError
            self.saved.append((block_id, content.text, time.monotonic()))
        return True


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
def queue(recorder: Recorder) -> Iterator[AutosaveQueue]:
    q = AutosaveQueue(recorder, delay_s=0.2)
    yield q
    q.close()


def _wait(condition: object, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():  # type: ignore[operator]  # a zero-argument callable
            return True
        time.sleep(0.01)
    return False


def test_edits_to_one_block_coalesce(queue: AutosaveQueue, recorder: Recorder) -> None:
    for text in ("T", "TX", "TXT"):
        queue.put(1, BlockContent(text=text))

    assert _wait(lambda: recorder.saved)
    time.sleep(0.3)
    assert [(b, t) for b, t, _ in recorder.saved] == [(1, "TXT")]


def test_continuous_typing_still_saves_regularly(queue: AutosaveQueue, recorder: Recorder) -> None:
    start = time.monotonic()
    count = 0
    while time.monotonic() - start < 1.0:
        count += 1
        queue.put(1, BlockContent(text="x" * count))
        time.sleep(0.02)

    # With a plain debounce nothing would save until typing stopped.
    assert len(recorder.saved) >= 3
    gaps = [b - a for (_, _, a), (_, _, b) in zip(recorder.saved, recorder.saved[1:], strict=False)]
    assert max(gaps) < 0.5


def test_flush_writes_everything_now(queue: AutosaveQueue, recorder: Recorder) -> None:
    queue.put(1, BlockContent(text="a"))
    queue.put(2, BlockContent(text="b"))

    assert queue.flush()
    assert sorted((b, t) for b, t, _ in recorder.saved) == [(1, "a"), (2, "b")]
    assert queue.pending == 0


def test_close_saves_what_is_left(recorder: Recorder) -> None:
    q = AutosaveQueue(recorder, delay_s=10)
    q.put(7, BlockContent(text="last words"))

    assert q.close()
    assert [(b, t) for b, t, _ in recorder.saved] == [(7, "last words")]


def test_failed_write_is_retried_not_dropped(recorder: Recorder) -> None:
    errors: list[Exception] = []
    q = AutosaveQueue(recorder, delay_s=0.05, on_error=errors.append)
    recorder.fail_next = 1
    q.put(1, BlockContent(text="keep me"))

    assert _wait(lambda: recorder.saved, timeout=3)
    assert [(b, t) for b, t, _ in recorder.saved] == [(1, "keep me")]
    assert len(errors) == 1
    q.close()


def test_newer_edit_wins_over_a_retry(recorder: Recorder) -> None:
    q = AutosaveQueue(recorder, delay_s=0.05)
    recorder.fail_next = 1
    q.put(1, BlockContent(text="old"))
    _wait(lambda: recorder.fail_next == 0)
    q.put(1, BlockContent(text="new"))

    assert q.flush()
    assert [t for _, t, _ in recorder.saved] == ["new"]
    q.close()


def test_autosave_writes_to_the_real_database(db: Database) -> None:
    rooms, tasks, blocks = RoomRepository(db), TaskRepository(db), BlockRepository(db)
    task = tasks.for_room(rooms.create(NewRoom(name="R", task_count=1)).id)[0]
    block = blocks.ensure_starter_block(task.id)
    q = AutosaveQueue(blocks.update_content, delay_s=0.05)

    q.put(block.id, BlockContent(text="TXT records hold text"))
    q.close()

    stored = blocks.get(block.id)
    assert stored is not None
    assert stored.content.text == "TXT records hold text"


# Daily snapshot ---------------------------------------------------------------


def _with_data(db: Database) -> None:
    RoomRepository(db).create(NewRoom(name="Snapshot me", task_count=2))


def test_snapshot_is_a_complete_private_database(db: Database, data_dir: Path) -> None:
    _with_data(db)
    folder = data_dir / "backups" / "db"

    path = backup.snapshot_if_due(db, folder, date(2026, 10, 25))

    assert path == folder / "app-2026-10-25.db"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    copy = sqlite3.connect(path)
    assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert copy.execute("SELECT name FROM rooms").fetchall() == [("Snapshot me",)]
    assert copy.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    copy.close()
    assert list(folder.glob(".*")) == []


def test_one_snapshot_per_day(db: Database, data_dir: Path) -> None:
    folder = data_dir / "backups" / "db"
    day = date(2026, 10, 25)

    assert backup.snapshot_if_due(db, folder, day) is not None
    assert backup.snapshot_if_due(db, folder, day) is None


def test_only_the_newest_fourteen_are_kept(db: Database, data_dir: Path) -> None:
    folder = data_dir / "backups" / "db"
    start = date(2026, 10, 1)
    for offset in range(20):
        backup.snapshot_if_due(db, folder, start + timedelta(days=offset))

    kept = sorted(p.name for p in folder.glob("app-*.db"))
    assert len(kept) == 14
    assert kept[0] == backup.snapshot_name(start + timedelta(days=6))
    assert kept[-1] == backup.snapshot_name(start + timedelta(days=19))


def test_prune_ignores_other_files(data_dir: Path) -> None:
    folder = data_dir / "b"
    folder.mkdir()
    (folder / "notes.txt").write_text("not a snapshot")
    for day in range(1, 4):
        (folder / f"app-2026-10-0{day}.db").write_text("x")

    removed = backup.prune(folder, keep=1)

    assert [p.name for p in removed] == ["app-2026-10-01.db", "app-2026-10-02.db"]
    assert (folder / "notes.txt").exists()


def test_failed_snapshot_raises_and_leaves_nothing(
    db: Database, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = data_dir / "backups" / "db"

    def broken(_db: Database, _temp: Path) -> None:
        raise sqlite3.OperationalError

    monkeypatch.setattr(backup, "_write_snapshot", broken)

    with pytest.raises(StorageError):
        backup.snapshot_if_due(db, folder, date(2026, 10, 25))

    assert list(folder.iterdir()) == []
