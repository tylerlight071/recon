"""pipeline.Pipeline: a queued room goes through three plain steps to staged notes."""

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel

from recon.config import Settings
from recon.db.connection import Database
from recon.db.migrate import migrate
from recon.db.repositories import BlockRepository, RoomRepository, TaskRepository
from recon.db.runs import RunRepository
from recon.errors import OllamaUnavailable
from recon.pipeline import Pipeline, Step
from recon.processing import Processing
from recon.services.runs import RunLog, RunStore
from tests.db.test_schema import insert_fixture_rooms
from tests.engine.pipeline import recorded

NUMBERS = 1  # the number_systems fixture room's ID


class FakeModel:
    """Replies with the recorded extract for number_systems, or raises."""

    def __init__(self) -> None:
        self.error: Exception | None = None
        self.during: Callable[[], None] = lambda: None
        self.calls: list[tuple[str, bool]] = []

    def structured[T: BaseModel](  # noqa: PLR0913 - mirrors OllamaService.structured
        self,
        *,
        model: str,
        schema: type[T],
        system: str,
        prompt: str,
        run: RunLog | None = None,
        step: str = "call",
        think: bool = False,
        context: int = 0,
    ) -> T:
        del system, prompt, run, step, context
        self.calls.append((model, think))
        self.during()
        if self.error is not None:
            raise self.error
        return schema.model_validate(recorded("number_systems").model_dump())


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database.open(tmp_path / "app.db")
    migrate(database)
    insert_fixture_rooms(database)
    yield database
    database.close()


def _pipeline(tmp_path: Path, db: Database, model: FakeModel) -> Pipeline:
    settings = Settings(model_thinking=True, vault_path=str(tmp_path / "vault"))
    (tmp_path / "vault").mkdir(exist_ok=True)

    def processing_for(current: Settings) -> Processing:
        return Processing(
            Path(current.vault_path),
            RunStore(tmp_path / "runs", lambda: datetime(2026, 10, 28, tzinfo=UTC), lambda: "ab"),
            tmp_path / "backups",
            RoomRepository(db),
            RunRepository(db),
        )

    return Pipeline(
        RoomRepository(db),
        TaskRepository(db),
        BlockRepository(db),
        lambda: settings,
        processing_for,
        lambda _host: model,
        lambda: date(2026, 10, 28),
    )


def _queue(db: Database, room_id: int = NUMBERS) -> None:
    RoomRepository(db).update_progress(room_id, status="queued")


def _status(db: Database, room_id: int = NUMBERS) -> str:
    room = RoomRepository(db).get(room_id)
    return room.status if room else "gone"


def test_a_queued_room_is_staged_for_review(tmp_path: Path, db: Database) -> None:
    model = FakeModel()
    pipeline = _pipeline(tmp_path, db, model)
    _queue(db)
    steps: list[Step] = []
    statuses: list[str] = []
    model.during = lambda: statuses.append(_status(db))

    outcome = pipeline.run(NUMBERS, steps.append, lambda: False)

    assert outcome.room == "Number Systems"
    assert outcome.manifest is not None
    assert (outcome.problem, outcome.cancelled) == ("", False)
    assert [(s.number, s.text) for s in steps] == [
        (1, "Reading your notes"),
        (2, "Structuring 4 tasks with qwen3.5:9b"),
        (3, f"Preparing {len(outcome.manifest.files)} notes for review"),
    ]
    assert statuses == ["processing"]
    assert model.calls == [("qwen3.5:9b", True)]
    assert _status(db) == "in_review"
    assert list((tmp_path / "vault").iterdir()) == []  # nothing before Apply
    assert (tmp_path / "runs" / "20261028T000000-ab" / "staged" / "manifest.json").exists()


def test_a_model_problem_puts_the_room_back_in_the_queue(tmp_path: Path, db: Database) -> None:
    model = FakeModel()
    model.error = OllamaUnavailable()
    _queue(db)

    outcome = _pipeline(tmp_path, db, model).run(NUMBERS, lambda _s: None, lambda: False)

    assert outcome.problem == OllamaUnavailable.user_message
    assert outcome.manifest is None
    assert _status(db) == "queued"


def test_cancelling_between_steps_leaves_the_room_for_next_time(
    tmp_path: Path, db: Database
) -> None:
    model = FakeModel()
    _queue(db)

    outcome = _pipeline(tmp_path, db, model).run(NUMBERS, lambda _s: None, lambda: True)

    assert outcome.cancelled is True
    assert model.calls == []
    assert _status(db) == "processing"


def test_cancelling_during_the_model_call_stages_nothing(tmp_path: Path, db: Database) -> None:
    model = FakeModel()
    stop = {"now": False}
    model.during = lambda: stop.update(now=True)
    _queue(db)

    outcome = _pipeline(tmp_path, db, model).run(NUMBERS, lambda _s: None, lambda: stop["now"])

    assert outcome.cancelled is True
    assert not (tmp_path / "runs" / "20261028T000000-ab" / "staged").exists()


def test_a_room_taken_back_mid_run_is_not_staged(tmp_path: Path, db: Database) -> None:
    model = FakeModel()
    model.during = lambda: RoomRepository(db).update_progress(NUMBERS, status="capturing")
    _queue(db)

    outcome = _pipeline(tmp_path, db, model).run(NUMBERS, lambda _s: None, lambda: False)

    assert outcome.cancelled is True
    assert _status(db) == "capturing"
    assert RunRepository(db).for_room(NUMBERS) == []


@pytest.mark.parametrize("room_id", [NUMBERS, 9999])
def test_only_queued_rooms_are_processed(tmp_path: Path, db: Database, room_id: int) -> None:
    model = FakeModel()  # number_systems is still capturing; 9999 doesn't exist

    outcome = _pipeline(tmp_path, db, model).run(room_id, lambda _s: None, lambda: False)

    assert outcome.cancelled is True
    assert model.calls == []


def test_a_room_deleted_mid_run_is_a_calm_problem(tmp_path: Path, db: Database) -> None:
    def delete(_step: Step) -> None:
        with db.transaction() as conn:
            conn.execute("DELETE FROM rooms WHERE id = ?", (NUMBERS,))

    _queue(db)

    outcome = _pipeline(tmp_path, db, FakeModel()).run(NUMBERS, delete, lambda: False)

    assert outcome.problem
    assert outcome.manifest is None


def test_one_task_is_singular(tmp_path: Path, db: Database) -> None:
    with db.transaction() as conn:
        conn.execute("DELETE FROM blocks WHERE task_id IN (102, 103, 104)")
    _queue(db)
    steps: list[Step] = []

    _pipeline(tmp_path, db, FakeModel()).run(NUMBERS, steps.append, lambda: False)

    assert steps[1].text == "Structuring 1 task with qwen3.5:9b"


@pytest.mark.ollama
def test_a_fixture_room_processes_end_to_end_on_the_real_model(
    tmp_path: Path, db: Database
) -> None:
    from recon.engine.stage import load_manifest  # noqa: PLC0415
    from recon.services.ollama import OllamaService, make_client  # noqa: PLC0415

    pipeline = _pipeline(tmp_path, db, FakeModel())
    real = Pipeline(
        pipeline.rooms,
        pipeline.tasks,
        pipeline.blocks,
        lambda: Settings(vault_path=str(tmp_path / "vault")),
        pipeline.processing_for,
        lambda host: OllamaService(make_client(host)),
        pipeline.today,
    )
    _queue(db)

    outcome = real.run(NUMBERS, lambda _s: None, lambda: False)

    assert outcome.problem == ""
    assert outcome.manifest is not None
    kinds = {f.kind for f in load_manifest(tmp_path / "runs" / outcome.manifest.run_id).files}
    assert {"room", "raw", "concept"} <= kinds
    assert _status(db) == "in_review"
    assert (tmp_path / "runs" / outcome.manifest.run_id / "extract-1.json").exists()
