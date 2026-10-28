"""Rooms, tasks and blocks through their repositories."""

import pytest

from recon.db.connection import Database
from recon.db.models import BlockContent, NewRoom
from recon.db.repositories import BlockRepository, RoomRepository, TaskRepository
from tests.db.conftest import FakeClock


@pytest.fixture
def repos(db: Database, clock: FakeClock) -> tuple[RoomRepository, TaskRepository, BlockRepository]:
    return RoomRepository(db, clock), TaskRepository(db, clock), BlockRepository(db, clock)


def test_new_room_gets_its_tasks(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository],
) -> None:
    rooms, tasks, _blocks = repos

    room = rooms.create(
        NewRoom(name="DNS in Detail", task_count=7, path="Pre Security", module="Networking")
    )

    assert (room.status, room.mode, room.last_task_index, room.time_spent_s) == (
        "capturing",
        "new",
        1,
        0,
    )
    assert [t.task_index for t in tasks.for_room(room.id)] == list(range(1, 8))
    assert all((t.title, t.status) == ("", "open") for t in tasks.for_room(room.id))


def test_unknown_ids(repos: tuple[RoomRepository, TaskRepository, BlockRepository]) -> None:
    rooms, tasks, blocks = repos

    assert rooms.get(42) is None
    assert rooms.update_progress(42, last_task_index=2) is False
    assert tasks.set_title(42, "x") is False
    assert blocks.get(42) is None
    assert blocks.update_content(42, BlockContent(text="x")) is False
    assert blocks.move(42, 0) is False
    assert blocks.delete(42) is None


def test_recent_rooms_are_newest_touched_first(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository], clock: FakeClock
) -> None:
    rooms, tasks, _blocks = repos
    first = rooms.create(NewRoom(name="First", task_count=1))
    clock.advance(60)
    second = rooms.create(NewRoom(name="Second", task_count=1))
    clock.advance(60)

    tasks.set_title(tasks.for_room(first.id)[0].id, "Ports")

    assert [r.name for r in rooms.recent()] == ["First", "Second"]
    assert [r.name for r in rooms.recent(limit=1)] == ["First"]
    assert second.id != first.id


def test_progress_is_recorded(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository], clock: FakeClock
) -> None:
    rooms, _tasks, _blocks = repos
    room = rooms.create(NewRoom(name="R", task_count=3))
    clock.advance(30)

    rooms.update_progress(room.id, last_task_index=2, add_time_s=90)
    rooms.update_progress(room.id, add_time_s=10, status="queued")

    updated = rooms.get(room.id)
    assert updated is not None
    assert (updated.last_task_index, updated.time_spent_s, updated.status) == (2, 100, "queued")
    assert updated.updated_at == clock.now


def test_task_title_and_status(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository],
) -> None:
    rooms, tasks, _blocks = repos
    task = tasks.for_room(rooms.create(NewRoom(name="R", task_count=2)).id)[1]

    assert tasks.set_title(task.id, "What is DNS?")
    assert tasks.set_status(task.id, "skipped")

    stored = tasks.for_room(task.room_id)[1]
    assert (stored.title, stored.status) == ("What is DNS?", "skipped")


def test_starter_block_is_placed_once(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository],
) -> None:
    rooms, tasks, blocks = repos
    task = tasks.for_room(rooms.create(NewRoom(name="R", task_count=1)).id)[0]

    first = blocks.ensure_starter_block(task.id)
    again = blocks.ensure_starter_block(task.id)

    assert first.id == again.id
    assert (first.type, first.content.text, first.phase, first.position) == (
        "key_idea",
        "",
        "fill",
        0,
    )
    assert len(blocks.for_task(task.id)) == 1


def test_recall_pass_blocks(repos: tuple[RoomRepository, TaskRepository, BlockRepository]) -> None:
    rooms, tasks, blocks = repos
    task = tasks.for_room(rooms.create(NewRoom(name="R", task_count=1, mode="from_memory")).id)[0]

    assert blocks.ensure_starter_block(task.id, phase="recall").phase == "recall"


def test_content_round_trips(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository], clock: FakeClock
) -> None:
    rooms, tasks, blocks = repos
    room = rooms.create(NewRoom(name="R", task_count=1))
    task = tasks.for_room(room.id)[0]
    block = blocks.add(task.id, "room_question")
    clock.advance(5)

    assert blocks.update_content(
        block.id, BlockContent(text="Which port does HTTPS use?", answer="443")
    )

    stored = blocks.get(block.id)
    assert stored is not None
    assert (stored.content.text, stored.content.answer) == ("Which port does HTTPS use?", "443")
    assert stored.updated_at == clock.now
    refreshed = rooms.get(room.id)
    assert refreshed is not None
    assert refreshed.updated_at == clock.now


def test_move_and_delete_keep_positions_tidy(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository],
) -> None:
    rooms, tasks, blocks = repos
    task = tasks.for_room(rooms.create(NewRoom(name="R", task_count=1)).id)[0]
    a, b, c = (blocks.add(task.id, "key_idea", BlockContent(text=t)) for t in "abc")

    assert blocks.move(c.id, 0)
    assert [x.content.text for x in blocks.for_task(task.id)] == ["c", "a", "b"]
    assert blocks.move(c.id, 99)
    assert [x.content.text for x in blocks.for_task(task.id)] == ["a", "b", "c"]

    deleted = blocks.delete(a.id)

    assert deleted is not None
    assert deleted.content.text == "a"
    remaining = blocks.for_task(task.id)
    assert [(x.content.text, x.position) for x in remaining] == [("b", 0), ("c", 1)]
    assert b.id in {x.id for x in remaining}


def test_text_is_stored_as_typed(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository],
) -> None:
    rooms, tasks, blocks = repos
    task = tasks.for_room(rooms.create(NewRoom(name="R", task_count=1)).id)[0]
    tricky = '\'); DROP TABLE rooms; -- é中 \N{EM DASH} "quoted"\n\ttabbed'
    block = blocks.add(task.id, "command", BlockContent(text=tricky))

    stored = blocks.get(block.id)

    assert stored is not None
    assert stored.content.text == tricky
    assert rooms.get(task.room_id) is not None


def test_rooms_in_the_vault_are_done_rooms_newest_first(db: Database) -> None:
    clock = FakeClock()
    rooms = RoomRepository(db, clock)
    first = rooms.create(NewRoom(name="First", task_count=1))
    rooms.create(NewRoom(name="Still capturing", task_count=1))
    rooms.update_progress(first.id, status="done")
    clock.advance(60)
    second = rooms.create(NewRoom(name="Second", task_count=1))
    rooms.update_progress(second.id, status="done")

    assert [r.name for r in rooms.in_vault()] == ["Second", "First"]
