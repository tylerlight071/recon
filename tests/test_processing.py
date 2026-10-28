"""processing.Processing: runs recorded and rooms moved along as notes are staged and applied."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from recon.__main__ import tidy_runs
from recon.config import Settings
from recon.db.connection import Database
from recon.db.migrate import migrate
from recon.db.models import NewRoom
from recon.db.repositories import RoomRepository
from recon.db.runs import RunRepository
from recon.engine.extract import check
from recon.engine.notes import Rendered, render_room
from recon.engine.stage import JOURNAL, Journal
from recon.errors import ApplyConflict
from recon.paths import AppPaths
from recon.processing import Processing
from recon.services.runs import RunStore
from tests.engine.pipeline import capture_of, recorded


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database.open(tmp_path / "app.db")
    migrate(database)
    yield database
    database.close()


def _processing(tmp_path: Path, db: Database, when: datetime | None = None) -> Processing:
    ids = iter(f"{n:04x}" for n in range(1, 100))
    clock = (lambda: when) if when else (lambda: datetime(2026, 10, 28, 12, 0, tzinfo=UTC))
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    return Processing(
        vault,
        RunStore(tmp_path / "data" / "runs", clock, lambda: next(ids)),
        tmp_path / "data" / "backups",
        RoomRepository(db),
        RunRepository(db),
    )


def _rendered() -> Rendered:
    capture = capture_of("number_systems")
    return render_room(capture, check(recorded("number_systems"), capture))


def _room(db: Database) -> int:
    return RoomRepository(db).create(NewRoom(name="Number Systems", task_count=5)).id


def test_stage_then_apply(tmp_path: Path, db: Database) -> None:
    processing = _processing(tmp_path, db)
    room = _room(db)
    run = processing.runs.start()

    manifest = processing.stage_room(room, _rendered(), run)

    assert RoomRepository(db).get(room).status == "in_review"  # type: ignore[union-attr]  # exists
    assert [r.status for r in processing.records.for_room(room)] == ["staged"]
    assert list(processing.vault.iterdir()) == []

    applied = processing.apply_run(run.run_id)

    assert applied.written == len(manifest.files)
    record = processing.records.get(run.run_id)
    assert record is not None
    assert (record.status, record.written) == ("applied", applied.written)
    assert RoomRepository(db).get(room).status == "done"  # type: ignore[union-attr]  # exists


def test_a_conflict_records_nothing(tmp_path: Path, db: Database) -> None:
    processing = _processing(tmp_path, db)
    room = _room(db)
    run = processing.runs.start()
    processing.stage_room(room, _rendered(), run)
    (processing.vault / "02 Concepts").mkdir()
    (processing.vault / "02 Concepts" / "Binary.md").write_text("made in Obsidian meanwhile")

    with pytest.raises(ApplyConflict):
        processing.apply_run(run.run_id)

    assert processing.records.get(run.run_id).status == "staged"  # type: ignore[union-attr]  # exists
    assert RoomRepository(db).get(room).status == "in_review"  # type: ignore[union-attr]  # exists


def test_discard_returns_the_room_to_capturing(tmp_path: Path, db: Database) -> None:
    processing = _processing(tmp_path, db)
    room = _room(db)
    run = processing.runs.start()
    processing.stage_room(room, _rendered(), run)

    processing.discard_run(run.run_id)

    assert RoomRepository(db).get(room).status == "capturing"  # type: ignore[union-attr]  # exists
    assert processing.records.get(run.run_id).status == "discarded"  # type: ignore[union-attr]  # exists
    assert list(processing.vault.iterdir()) == []


def test_start_up_finishes_an_interrupted_apply_and_keeps_waiting_runs(
    tmp_path: Path, db: Database
) -> None:
    long_ago = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
    old = _processing(tmp_path, db, long_ago)
    room = _room(db)
    crashed, waiting, expired = old.runs.start(), old.runs.start(), old.runs.start()
    old.stage_room(room, _rendered(), crashed)
    (crashed.folder / JOURNAL).write_text(Journal(state="applying").model_dump_json())
    waiting_room = RoomRepository(db).create(NewRoom(name="Waiting", task_count=1)).id
    old.stage_room(waiting_room, Rendered(notes=()), waiting)
    expired.record("extract", 1, {})
    paths = AppPaths(data=tmp_path / "data", config=tmp_path / "config", cache=tmp_path / "cache")

    tidy_runs(paths, Settings(vault_path=str(old.vault)), db)

    assert RoomRepository(db).get(room).status == "done"  # type: ignore[union-attr]  # exists
    assert old.records.get(crashed.run_id).status == "applied"  # type: ignore[union-attr]  # exists
    assert (old.vault / "02 Concepts" / "Binary.md").exists()
    assert not expired.folder.exists()
    assert not crashed.folder.exists()  # applied and over 30 days old
    assert waiting.folder.exists()  # still waiting for the user


def test_start_up_logs_and_carries_on_when_tidying_fails(
    tmp_path: Path, db: Database, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def refuse(_self: RunStore, **_: object) -> int:
        raise PermissionError

    monkeypatch.setattr(RunStore, "prune", refuse)
    paths = AppPaths(data=tmp_path / "data", config=tmp_path / "config", cache=tmp_path / "cache")

    tidy_runs(paths, Settings(vault_path=str(tmp_path / "vault")), db)

    assert "old runs not tidied: PermissionError" in caplog.text


def test_a_run_that_cannot_be_recovered_is_logged(
    tmp_path: Path, db: Database, caplog: pytest.LogCaptureFixture
) -> None:
    processing = _processing(tmp_path, db)
    room = _room(db)
    run = processing.runs.start()
    processing.stage_room(room, _rendered(), run)
    (run.folder / JOURNAL).write_text(Journal(state="applying").model_dump_json())
    (run.folder / "staged" / "manifest.json").write_text("{broken")

    assert processing.recover_runs() == 0
    assert "not recovered: StagingDamagedError" in caplog.text


def test_back_to_the_room_discards_every_staged_run(tmp_path: Path, db: Database) -> None:
    processing = _processing(tmp_path, db)
    room = _room(db)
    first, second = processing.runs.start(), processing.runs.start()
    processing.stage_room(room, _rendered(), first)
    processing.stage_room(room, _rendered(), second)
    processing.discard_run(first.run_id)

    assert processing.discard_room(room) == 1
    assert not (second.folder / "staged").exists()
    assert {r.status for r in processing.records.for_room(room)} == {"discarded"}
