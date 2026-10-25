"""Restoring deleted blocks, and the undo log (task 1.11)."""

import pytest

from recon.db.connection import Database
from recon.db.models import (
    Block,
    BlockContent,
    InsertBlock,
    MoveBlock,
    NewRoom,
    RemoveBlock,
    SetContent,
)
from recon.db.repositories import BlockRepository, RoomRepository, TaskRepository, UndoRepository
from tests.db.conftest import FakeClock


@pytest.fixture
def blocks(db: Database, clock: FakeClock) -> BlockRepository:
    return BlockRepository(db, clock)


@pytest.fixture
def undo(db: Database, clock: FakeClock) -> UndoRepository:
    return UndoRepository(db, clock)


def _task(db: Database, clock: FakeClock, name: str = "R") -> tuple[int, int]:
    room = RoomRepository(db, clock).create(NewRoom(name=name, task_count=2))
    return room.id, TaskRepository(db, clock).for_room(room.id)[0].id


def _three(blocks: BlockRepository, task_id: int) -> list[Block]:
    return [
        blocks.add(task_id, "key_idea", BlockContent(text="one")),
        blocks.add(task_id, "command", BlockContent(text="two")),
        blocks.add(task_id, "question", BlockContent(text="three")),
    ]


# Restore -----------------------------------------------------------------------------------


def test_restore_puts_a_block_back_with_its_id_and_place(
    db: Database, clock: FakeClock, blocks: BlockRepository
) -> None:
    _room, task = _task(db, clock)
    two = _three(blocks, task)[1]
    deleted = blocks.delete(two.id)
    assert deleted is not None

    restored = blocks.restore(deleted)

    assert restored.id == two.id
    assert [(b.content.text, b.position) for b in blocks.for_task(task)] == [
        ("one", 0),
        ("two", 1),
        ("three", 2),
    ]
    assert restored.created_at == two.created_at


def test_restore_gets_a_new_id_if_the_old_one_was_reused(
    db: Database, clock: FakeClock, blocks: BlockRepository
) -> None:
    _room, task = _task(db, clock)
    _one, _two, three = _three(blocks, task)
    deleted = blocks.delete(three.id)
    assert deleted is not None
    reused = blocks.add(task, "table")  # SQLite hands out the highest free ID again
    assert reused.id == three.id

    restored = blocks.restore(deleted)

    assert restored.id != three.id
    assert [b.content.text for b in blocks.for_task(task)] == ["one", "two", "three", ""]


def test_restore_clamps_the_position(
    db: Database, clock: FakeClock, blocks: BlockRepository
) -> None:
    _room, task = _task(db, clock)
    one = blocks.add(task, "key_idea", BlockContent(text="one"))
    deleted = blocks.delete(one.id)
    assert deleted is not None

    restored = blocks.restore(deleted.model_copy(update={"position": 9}))

    assert restored.position == 0


def test_restore_strips_flags(db: Database, clock: FakeClock, blocks: BlockRepository) -> None:
    _room, task = _task(db, clock)
    block = blocks.add(task, "key_idea")
    deleted = blocks.delete(block.id)
    assert deleted is not None
    sneaky = deleted.model_copy(update={"content": BlockContent(text="x THM{y}")})

    assert blocks.restore(sneaky).content.text == "x "


# Undo log ---------------------------------------------------------------------------------


def test_steps_round_trip_in_order(
    db: Database, clock: FakeClock, blocks: BlockRepository, undo: UndoRepository
) -> None:
    room, task = _task(db, clock)
    block = blocks.add(task, "key_idea", BlockContent(text="one"))
    actions = [
        SetContent(block_id=block.id, content=BlockContent(text="before", answer="53")),
        RemoveBlock(block_id=block.id),
        InsertBlock(block=block),
        MoveBlock(block_id=block.id, position=2),
    ]

    pushed = [undo.push(room, task, action) for action in actions]

    loaded = undo.for_room(room)
    assert [e.action for e in loaded] == actions
    assert [e.id for e in loaded] == [e.id for e in pushed]
    assert {(e.room_id, e.task_id) for e in loaded} == {(room, task)}


def test_steps_are_per_room(
    db: Database, clock: FakeClock, blocks: BlockRepository, undo: UndoRepository
) -> None:
    room, task = _task(db, clock, "A")
    other, other_task = _task(db, clock, "B")
    undo.push(room, task, RemoveBlock(block_id=1))
    undo.push(other, other_task, RemoveBlock(block_id=2))

    assert [e.action for e in undo.for_room(room)] == [RemoveBlock(block_id=1)]
    assert blocks.for_task(task) == []


def test_flags_never_reach_the_undo_log(
    db: Database, clock: FakeClock, blocks: BlockRepository, undo: UndoRepository
) -> None:
    room, task = _task(db, clock)
    block = blocks.add(task, "room_question")
    flagged = BlockContent(text="q THM{a}", answer="flag{b} 53")

    undo.push(room, task, SetContent(block_id=block.id, content=flagged))
    undo.push(room, task, InsertBlock(block=block.model_copy(update={"content": flagged})))

    with db.read() as conn:
        stored = " ".join(row[0] for row in conn.execute("SELECT before FROM undo_log"))
    assert "THM{" not in stored
    assert "flag{" not in stored
    first, second = undo.for_room(room)
    assert isinstance(first.action, SetContent)
    assert (first.action.content.text, first.action.content.answer) == ("q ", " 53")
    assert isinstance(second.action, InsertBlock)
    assert second.action.block.content.text == "q "


def test_delete_forgets_a_step(clock: FakeClock, db: Database, undo: UndoRepository) -> None:
    room, task = _task(db, clock)
    first = undo.push(room, task, RemoveBlock(block_id=1))
    undo.push(room, task, RemoveBlock(block_id=2))

    undo.delete(first.id)

    assert [e.action for e in undo.for_room(room)] == [RemoveBlock(block_id=2)]


def test_only_the_newest_steps_are_kept(
    clock: FakeClock, db: Database, undo: UndoRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    room, task = _task(db, clock)
    monkeypatch.setattr(UndoRepository, "KEEP_PER_ROOM", 3)
    for block_id in range(6):
        undo.push(room, task, RemoveBlock(block_id=block_id))

    assert [e.action for e in undo.for_room(room)] == [RemoveBlock(block_id=i) for i in (3, 4, 5)]


def test_remap_points_steps_at_a_restored_block(
    db: Database, clock: FakeClock, blocks: BlockRepository, undo: UndoRepository
) -> None:
    room, task = _task(db, clock)
    block = blocks.add(task, "key_idea")
    undo.push(room, task, SetContent(block_id=block.id, content=BlockContent(text="a")))
    undo.push(room, task, InsertBlock(block=block))
    undo.push(room, task, MoveBlock(block_id=999, position=0))

    undo.remap(room, block.id, 77)

    actions = [e.action for e in undo.for_room(room)]
    assert actions[0] == SetContent(block_id=77, content=BlockContent(text="a"))
    assert isinstance(actions[1], InsertBlock)
    assert actions[1].block.id == 77
    assert actions[2] == MoveBlock(block_id=999, position=0)
    with db.read() as conn:
        assert [r[0] for r in conn.execute("SELECT entity_id FROM undo_log ORDER BY id")] == [
            77,
            77,
            999,
        ]
