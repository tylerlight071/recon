"""RunRepository: each run recorded as staged, then applied or discarded once."""

from datetime import timedelta

from recon.db.connection import Database
from recon.db.models import NewRoom
from recon.db.repositories import RoomRepository
from recon.db.runs import RunRepository
from tests.db.conftest import FakeClock


def _room(db: Database) -> int:
    return RoomRepository(db).create(NewRoom(name="DNS in Detail", task_count=2)).id


def test_a_run_is_staged_then_applied_once(db: Database) -> None:
    clock = FakeClock()
    runs = RunRepository(db, clock)
    room = _room(db)

    run = runs.start("20261025T090000-aa", room)
    clock.advance(60)

    assert (run.status, run.finished_at, run.written) == ("staged", None, 0)
    assert runs.staged() == [run]
    assert runs.applied(run.id, written=5, backed_up=2) is True
    assert runs.applied(run.id, written=9, backed_up=9) is False  # only once
    assert runs.discarded(run.id) is False
    done = runs.get(run.id)
    assert done is not None
    assert (done.status, done.written, done.backed_up) == ("applied", 5, 2)
    assert done.finished_at == clock.now
    assert runs.staged() == []


def test_discarded_runs_and_newest_first(db: Database) -> None:
    clock = FakeClock()
    runs = RunRepository(db, clock)
    room = _room(db)
    first = runs.start("20261025T090000-aa", room)
    clock.advance(timedelta(hours=1).total_seconds())
    second = runs.start("20261025T100000-bb", room)

    assert runs.discarded(first.id) is True

    assert [r.id for r in runs.for_room(room)] == [second.id, first.id]
    assert runs.for_room(room)[1].status == "discarded"
    assert runs.get("nope") is None
    assert [r.id for r in runs.staged()] == [second.id]
