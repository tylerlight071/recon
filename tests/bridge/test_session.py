"""RoomSessionBridge: open a room, edit safely, add blocks, move through tasks."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from PySide6.QtCore import QObject

from recon.bridge.blocks_model import BlockListModel
from recon.bridge.flags import FlagGuard
from recon.bridge.session import RoomSessionBridge
from recon.db.connection import Database
from recon.db.migrate import migrate
from recon.db.models import Block, BlockContent, BlockType, NewRoom, Room
from recon.db.repositories import BlockRepository, RoomRepository, TaskRepository
from recon.errors import ReconError, StorageError
from tests.bridge.fakes import FakeAutosave
from tests.db.conftest import FakeClock
from tests.ui.qml_harness import SignalCounter, app, wait_until

MD5 = "5d41402abc4b2a76b9719d911017c592"


class Monotonic:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class Held:
    """A submit that keeps jobs until told to run them."""

    def __init__(self) -> None:
        self.jobs: list[Callable[[], None]] = []

    def __call__(self, job: Callable[[], None]) -> None:
        self.jobs.append(job)

    def run(self) -> None:
        jobs, self.jobs = self.jobs, []
        for job in jobs:
            job()


@dataclass
class World:
    session: RoomSessionBridge
    rooms: RoomRepository
    tasks: TaskRepository
    blocks: BlockRepository
    autosave: FakeAutosave
    guard: FlagGuard
    clock: Monotonic
    focused: list[int]
    finished: list[int]
    failures: list[str]

    def room(self, name: str = "DNS in Detail", tasks: int = 3) -> Room:
        return self.rooms.create(NewRoom(name=name, task_count=tasks))

    def opened(self, tasks: int = 3) -> Room:
        room = self.room(tasks=tasks)
        self.session.open(room.id)
        return room

    def shown(self) -> list[Block]:
        model = self.session.property("blocks")
        assert isinstance(model, QObject)
        task = self.tasks.for_room(self.room_id())[self.session.property("taskIndex") - 1]
        return self.blocks.for_task(task.id)

    def room_id(self) -> int:
        room = self.rooms.current()
        assert room is not None
        return room.id


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    folder = tmp_path / "recon"
    folder.mkdir(mode=0o700)
    database = Database.open(folder / "app.db")
    migrate(database)
    yield database
    database.close()


def _world(
    db: Database,
    submit: Callable[[Callable[[], None]], None] | None = None,
    blocks: BlockRepository | None = None,
) -> World:
    app()
    clock = FakeClock()
    rooms, tasks = RoomRepository(db, clock), TaskRepository(db, clock)
    blocks = blocks or BlockRepository(db, clock)
    autosave = FakeAutosave(blocks)
    guard = FlagGuard(blocks.keep_lookalike)
    monotonic = Monotonic()
    session = RoomSessionBridge(
        (rooms, tasks, blocks),
        autosave,
        guard,
        submit=submit or (lambda job: job()),
        monotonic=monotonic,
    )
    world = World(session, rooms, tasks, blocks, autosave, guard, monotonic, [], [], [])
    session.focusBlock.connect(world.focused.append)
    session.finishRequested.connect(world.finished.append)
    session.failed.connect(world.failures.append)
    return world


@pytest.fixture
def world(db: Database) -> World:
    return _world(db)


# Opening ------------------------------------------------------------------------------


def test_nothing_open_at_first(world: World) -> None:
    session = world.session

    assert session.property("hasRoom") is False
    assert (session.property("roomName"), session.property("taskLabel")) == ("", "")
    assert (session.property("titleHint"), session.property("taskTitle")) == ("", "")
    assert session.property("progress") == 0.0
    assert session.property("elapsed") == 0
    assert session.property("isLastTask") is False


def test_opening_shows_task_one_with_a_key_idea_ready(world: World) -> None:
    room = world.opened()
    session = world.session

    assert session.property("hasRoom") is True
    assert session.property("roomName") == "DNS in Detail"
    assert session.property("taskLabel") == "Task 1 of 3"
    assert (session.property("taskIndex"), session.property("taskCount")) == (1, 3)
    assert session.property("titleHint") == "Task 1"
    assert session.property("primaryText") == "Next task"
    shown = world.shown()
    assert [b.type for b in shown] == ["key_idea"]
    assert world.focused == [shown[0].id]
    assert room.id == world.room_id()


def test_opening_resumes_where_tyler_was(world: World) -> None:
    room = world.room(tasks=5)
    world.rooms.update_progress(room.id, last_task_index=4)

    world.session.open(room.id)

    assert world.session.property("taskLabel") == "Task 4 of 5"


def test_an_out_of_range_position_is_clamped(world: World, db: Database) -> None:
    room = world.room(tasks=2)
    with db.transaction() as conn:  # an older or edited database
        conn.execute("UPDATE rooms SET last_task_index = 9 WHERE id = ?", (room.id,))

    world.session.open(room.id)

    assert world.session.property("taskLabel") == "Task 2 of 2"


def test_finished_and_missing_rooms_do_not_open(world: World) -> None:
    room = world.room()
    world.rooms.update_progress(room.id, status="in_review")

    world.session.open(room.id)
    world.session.open(9999)

    assert world.session.property("hasRoom") is False


def test_time_on_the_room_counts_from_opening(world: World) -> None:
    world.opened()
    changed = SignalCounter(world.session, "elapsedChanged()")

    world.clock.now += 75

    assert world.session.property("elapsed") == 75
    assert wait_until(lambda: changed.count >= 1, timeout_ms=1500)


# Editing ------------------------------------------------------------------------------------


def test_edits_go_to_autosave(world: World) -> None:
    world.opened()
    block = world.shown()[0]

    shown = world.session.edit(block.id, "TXT records hold text")

    assert shown == "TXT records hold text"
    assert world.autosave.pending[block.id].text == "TXT records hold text"


def test_a_typed_flag_disappears_and_is_never_queued(world: World) -> None:
    world.opened()
    block = world.shown()[0]
    skipped = SignalCounter(world.guard, "flagSkipped(int,QString)")

    shown = world.session.edit(block.id, "answer THM{s3cret}")

    assert shown == "answer "
    assert "THM{" not in world.autosave.pending[block.id].text
    assert skipped.count == 1


def test_editing_a_block_from_another_task_is_ignored(world: World) -> None:
    world.opened()

    assert world.session.edit(9999, "text") == "text"
    assert world.autosave.pending == {}


def test_not_a_flag_keep_it_restores_the_hash_in_place(world: World) -> None:
    world.opened()
    block = world.shown()[0]
    world.session.edit(block.id, f"md5 of hello is {MD5} ok")
    replaced: list[tuple[int, str]] = []
    world.session.replaceText.connect(lambda i, _field, t: replaced.append((i, t)))

    world.guard.keep(block.id, MD5)

    assert replaced == [(block.id, f"md5 of hello is {MD5} ok")]
    pending = world.autosave.pending[block.id]
    assert (pending.text, pending.kept) == (f"md5 of hello is {MD5} ok", (MD5,))
    # Later edits keep it.
    assert world.session.edit(block.id, f"md5 of hello is {MD5} ok!") == (
        f"md5 of hello is {MD5} ok!"
    )


def test_keep_after_more_typing_adds_the_hash_at_the_end(world: World) -> None:
    world.opened()
    block = world.shown()[0]
    world.session.edit(block.id, f"hash {MD5}")
    world.session.edit(block.id, "hash  and more")
    replaced: list[tuple[int, str]] = []
    world.session.replaceText.connect(lambda i, _field, t: replaced.append((i, t)))

    world.guard.keep(block.id, MD5)

    assert replaced == [(block.id, f"hash  and more {MD5}")]


def test_keep_without_a_skip_changes_nothing(world: World) -> None:
    world.opened()
    block = world.shown()[0]
    world.session.edit(block.id, "plain")
    replaced = SignalCounter(world.session, "replaceText(int,QString,QString)")

    world.guard.keep(block.id, MD5)

    assert replaced.count == 0


def test_the_title_saves_shortly_after_typing(world: World) -> None:
    room = world.opened()

    world.session.setTitle("  Record types ")

    assert wait_until(lambda: world.tasks.for_room(room.id)[0].title == "Record types")
    assert world.session.property("taskTitle") == "Record types"


def test_set_title_without_a_room_does_nothing(world: World) -> None:
    world.session.setTitle("x")

    assert world.session.property("taskTitle") == ""


def test_close_saves_an_unsaved_title_now(world: World) -> None:
    room = world.opened()
    world.session.setTitle("Zones")

    world.session.close()

    assert world.tasks.for_room(room.id)[0].title == "Zones"


def test_close_with_nothing_pending_is_fine(world: World) -> None:
    world.session.close()
    world.opened()
    world.session.close()


# Adding blocks -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "block_type", ["command", "table", "question", "confused", "room_question"]
)
def test_add_a_block_and_put_the_cursor_in_it(world: World, block_type: BlockType) -> None:
    world.opened()

    world.session.addBlock(block_type)

    shown = world.shown()
    assert [b.type for b in shown] == ["key_idea", block_type]
    assert world.focused[-1] == shown[1].id
    model = world.session.property("blocks")
    assert model.rowCount() == 2


@pytest.mark.parametrize("block_type", ["voice", "screenshot", "nonsense"])
def test_blocks_not_ready_yet_are_not_added(world: World, block_type: str) -> None:
    world.opened()

    world.session.addBlock(block_type)

    assert len(world.shown()) == 1


def test_add_block_without_a_room_does_nothing(world: World) -> None:
    world.session.addBlock("key_idea")

    assert world.session.property("hasRoom") is False


def test_add_bar_lists_all_eight_in_a_fixed_order(world: World) -> None:
    bar = world.session.property("addBar")

    assert [entry["type"] for entry in bar] == [
        "key_idea",
        "command",
        "table",
        "screenshot",
        "question",
        "confused",
        "room_question",
        "voice",
    ]
    assert [e["type"] for e in bar if not e["available"]] == ["screenshot", "voice"]
    assert [e["shortcut"] for e in bar][:3] == ["Ctrl+1", "Ctrl+2", "Ctrl+3"]


# Moving on --------------------------------------------------------------------------------------


def test_next_task_ticks_saves_and_opens_the_next(world: World) -> None:
    room = world.opened()
    first = world.shown()[0]
    world.session.edit(first.id, "A records point at IPv4")
    world.session.setTitle("Records")
    ticks = SignalCounter(world.session, "taskCompleted()")

    world.session.next()

    tasks = world.tasks.for_room(room.id)
    assert [t.status for t in tasks] == ["done", "open", "open"]
    assert tasks[0].title == "Records"
    assert world.blocks.get(first.id).content.text == "A records point at IPv4"  # type: ignore[union-attr]
    assert world.autosave.flushes == 1
    assert ticks.count == 1
    assert world.session.property("taskLabel") == "Task 2 of 3"
    assert world.session.property("taskTitle") == ""
    assert world.session.property("progress") == pytest.approx(1 / 3)
    assert world.rooms.get(room.id).last_task_index == 2  # type: ignore[union-attr]
    second = world.shown()
    assert [b.type for b in second] == ["key_idea"]
    assert world.focused[-1] == second[0].id


def test_skip_moves_on_without_a_tick(world: World) -> None:
    room = world.opened()
    ticks = SignalCounter(world.session, "taskCompleted()")

    world.session.skip()

    assert [t.status for t in world.tasks.for_room(room.id)] == ["skipped", "open", "open"]
    assert ticks.count == 0
    assert world.session.property("taskLabel") == "Task 2 of 3"
    assert world.session.property("progress") == pytest.approx(1 / 3)


def test_the_last_task_offers_finish_room(world: World) -> None:
    room = world.opened(tasks=2)
    world.session.next()

    assert world.session.property("isLastTask") is True
    assert world.session.property("primaryText") == "Finish room"
    ticks = SignalCounter(world.session, "taskCompleted()")

    world.session.next()

    assert world.finished == [room.id]
    assert ticks.count == 1
    assert world.session.property("progress") == 1.0
    assert [t.status for t in world.tasks.for_room(room.id)] == ["done", "done"]


def test_skipping_the_last_task_also_finishes(world: World) -> None:
    room = world.opened(tasks=1)
    ticks = SignalCounter(world.session, "taskCompleted()")

    world.session.skip()

    assert world.finished == [room.id]
    assert ticks.count == 0


def test_moving_on_without_a_room_does_nothing(world: World) -> None:
    world.session.next()
    world.session.skip()

    assert world.finished == []


def test_busy_while_moving_on_and_a_second_press_is_ignored(db: Database) -> None:
    held = Held()
    world = _world(db, submit=held)
    room = world.room()
    world.session.open(room.id)
    held.run()
    busy = SignalCounter(world.session, "busyChanged()")

    world.session.next()
    world.session.next()
    world.session.addBlock("command")

    assert world.session.property("busy") is True
    assert len(held.jobs) == 1
    held.run()
    assert world.session.property("busy") is False
    assert busy.count == 2
    assert world.session.property("taskLabel") == "Task 2 of 3"


class BrokenBlocks(BlockRepository):
    def add(self, *_args: object, **_kwargs: object) -> Block:
        raise StorageError


class SurprisingBlocks(BlockRepository):
    def for_task(self, _task_id: int) -> list[Block]:
        raise RuntimeError


def test_a_failed_save_is_reported_calmly(db: Database) -> None:
    world = _world(db, blocks=BrokenBlocks(db))

    world.session.open(world.room().id)

    assert world.failures == [StorageError.user_message]
    assert world.session.property("busy") is False
    assert world.session.property("hasRoom") is False


def test_an_unexpected_failure_never_leaves_the_panel_stuck(db: Database) -> None:
    world = _world(db, blocks=SurprisingBlocks(db))

    world.session.open(world.room().id)

    assert world.failures == [ReconError.user_message]
    assert world.session.property("busy") is False


def test_a_failed_title_save_is_reported(db: Database) -> None:
    class BrokenTasks(TaskRepository):
        def set_title(self, _task_id: int, _title: str) -> bool:
            raise StorageError

    app()
    clock = FakeClock()
    blocks = BlockRepository(db, clock)
    rooms = RoomRepository(db, clock)
    session = RoomSessionBridge(
        (rooms, BrokenTasks(db, clock), blocks),
        FakeAutosave(blocks),
        FlagGuard(blocks.keep_lookalike),
        submit=lambda job: job(),
    )
    failures: list[str] = []
    session.failed.connect(failures.append)
    session.open(rooms.create(NewRoom(name="R", task_count=1)).id)

    session.setTitle("T")
    assert wait_until(lambda: failures != [])
    session.setTitle("T2")
    session.close()  # logged, not raised

    assert failures == [StorageError.user_message]


def test_unknown_content_is_kept_out_of_the_model(world: World) -> None:
    world.opened()
    model = world.session.property("blocks")

    assert model.set_content(9999, BlockContent(text="x"), notify=True) is False


def test_switching_rooms_saves_the_title_to_the_right_task(world: World) -> None:
    first = world.opened()
    world.session.setTitle("Zones")
    second = world.room(name="Linux Basics")
    shown = SignalCounter(world.session, "taskShown()")

    world.session.open(second.id)

    assert world.tasks.for_room(first.id)[0].title == "Zones"
    assert world.tasks.for_room(second.id)[0].title == ""
    assert world.session.property("taskTitle") == ""
    assert shown.count == 1


def test_previous_task_goes_back_without_changing_statuses(world: World) -> None:
    room = world.opened()
    world.session.next()
    world.session.skip()
    third = world.shown()[0]
    world.session.edit(third.id, "half a thought")
    world.session.setTitle("Zones")
    ticks = SignalCounter(world.session, "taskCompleted()")

    world.session.previous()

    assert world.session.property("taskLabel") == "Task 2 of 3"
    assert [t.status for t in world.tasks.for_room(room.id)] == ["done", "skipped", "open"]
    assert world.tasks.for_room(room.id)[2].title == "Zones"
    assert world.blocks.get(third.id).content.text == "half a thought"  # type: ignore[union-attr]
    assert world.rooms.get(room.id).last_task_index == 2  # type: ignore[union-attr]
    assert ticks.count == 0
    assert world.session.property("canGoBack") is True
    assert world.focused[-1] == world.shown()[0].id


def test_next_from_a_revisited_task_returns_to_its_notes(world: World) -> None:
    world.opened()
    world.session.next()
    second = world.shown()[0]
    world.session.edit(second.id, "kept")
    world.session.previous()

    world.session.next()

    assert world.session.property("taskLabel") == "Task 2 of 3"
    assert [b.id for b in world.shown()] == [second.id]
    model = world.session.property("blocks")
    assert model.data(model.index(0), BlockListModel.TextRole) == "kept"


def test_no_going_back_from_task_one(world: World) -> None:
    world.opened()

    assert world.session.property("canGoBack") is False
    world.session.previous()

    assert world.session.property("taskLabel") == "Task 1 of 3"
    assert world.autosave.flushes == 0


def test_previous_without_a_room_does_nothing(world: World) -> None:
    world.session.previous()

    assert world.session.property("canGoBack") is False


# Task 1.10: answers and moving blocks ---------------------------------------------------


def _room_question(world: World) -> Block:
    world.opened()
    world.session.addBlock("room_question")
    return world.shown()[1]


def test_answers_are_flag_filtered_and_autosaved(world: World) -> None:
    block = _room_question(world)
    world.session.edit(block.id, "What port does DNS use?")

    shown = world.session.editAnswer(block.id, "53, THM{d0nt}")

    assert shown == "53, "
    pending = world.autosave.pending[block.id]
    assert (pending.text, pending.answer) == ("What port does DNS use?", "53, ")
    assert world.session.editAnswer(9999, "x") == "x"


def test_keep_restores_a_hash_in_the_answer(world: World) -> None:
    block = _room_question(world)
    world.session.editAnswer(block.id, f"the hash is {MD5}")
    replaced: list[tuple[int, str, str]] = []
    world.session.replaceText.connect(lambda i, f, t: replaced.append((i, f, t)))

    world.guard.keep(block.id, MD5)

    assert replaced == [(block.id, "answer", f"the hash is {MD5}")]
    assert world.autosave.pending[block.id].answer == f"the hash is {MD5}"


def test_answers_come_back_with_the_task(world: World) -> None:
    block = _room_question(world)
    world.session.editAnswer(block.id, "53")
    world.session.next()

    world.session.previous()

    model = world.session.property("blocks")
    assert model.data(model.index(1), BlockListModel.AnswerRole) == "53"
    assert model.data(model.index(0), BlockListModel.AnswerRole) == ""


def test_move_block_reorders_the_task(world: World) -> None:
    world.opened()
    world.session.addBlock("command")
    world.session.addBlock("question")
    key, command, question = (b.id for b in world.shown())

    world.session.moveBlock(question, 0)

    assert [b.id for b in world.shown()] == [question, key, command]
    model = world.session.property("blocks")
    assert [model.data(model.index(i), BlockListModel.IdRole) for i in range(3)] == [
        question,
        key,
        command,
    ]
    assert world.focused[-1] == question


@pytest.mark.parametrize(("position", "order"), [(9, [1, 2, 0]), (-3, [0, 1, 2]), (1, [1, 0, 2])])
def test_move_block_clamps_and_moves_down(world: World, position: int, order: list[int]) -> None:
    world.opened()
    world.session.addBlock("command")
    world.session.addBlock("question")
    ids = [b.id for b in world.shown()]

    world.session.moveBlock(ids[0], position)

    assert [b.id for b in world.shown()] == [ids[i] for i in order]


def test_moving_nowhere_writes_nothing(world: World) -> None:
    world.opened()
    block = world.shown()[0]
    focused = len(world.focused)

    world.session.moveBlock(block.id, 0)
    world.session.moveBlock(9999, 0)

    assert len(world.focused) == focused
