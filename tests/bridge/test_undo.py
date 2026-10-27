"""UndoHistory: per-task stacks, typing grouped into words, and lookups."""

from datetime import UTC, datetime

from recon.bridge.undo import GROUP_PAUSE_S, UndoHistory
from recon.db.models import (
    Block,
    BlockContent,
    InsertBlock,
    RemoveBlock,
    UndoEntry,
)

WHEN = datetime(2026, 10, 25, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _history() -> tuple[UndoHistory, Clock]:
    clock = Clock()
    return UndoHistory(clock), clock


def _type(history: UndoHistory, text: str, *, block: int = 1, task: int = 10) -> int:
    """Type `text` one key at a time; returns how many steps started."""
    steps, typed = 0, ""
    for char in text:
        before = BlockContent(text=typed)
        typed += char
        if history.typed(task, block_id=block, field_name="text", before=before, new=typed):
            steps += 1
    return steps


def test_typing_is_one_step_per_word() -> None:
    history, _clock = _history()

    assert _type(history, "TXT records hold text") == 4
    befores = [s.action.content.text for s in history.undo[10]]  # type: ignore[union-attr]
    assert befores == ["", "TXT ", "TXT records ", "TXT records hold "]


def test_a_pause_starts_a_new_step() -> None:
    history, clock = _history()
    history.typed(10, block_id=1, field_name="text", before=BlockContent(), new="a")
    clock.now += GROUP_PAUSE_S

    step = history.typed(10, block_id=1, field_name="text", before=BlockContent(text="a"), new="ab")

    assert step is not None
    assert len(history.undo[10]) == 2


def test_another_block_or_field_starts_a_new_step() -> None:
    history, _clock = _history()
    history.typed(10, block_id=1, field_name="text", before=BlockContent(), new="a")

    assert history.typed(10, block_id=2, field_name="text", before=BlockContent(), new="b")
    assert history.typed(10, block_id=2, field_name="answer", before=BlockContent(), new="c")
    assert len(history.undo[10]) == 3


def test_answers_group_on_the_answer_text() -> None:
    history, _clock = _history()
    before = BlockContent(text="question", answer="5")

    assert history.typed(10, block_id=1, field_name="answer", before=before, new="53") is not None
    assert history.typed(10, block_id=1, field_name="answer", before=before, new="53 ") is None


def test_record_closes_the_group_and_clears_redo() -> None:
    history, _clock = _history()
    history.typed(10, block_id=1, field_name="text", before=BlockContent(), new="a")
    history.push_redo(10, RemoveBlock(block_id=5))

    history.record(10, RemoveBlock(block_id=2))

    assert history.redo.get(10) is None
    assert history.typed(10, block_id=1, field_name="text", before=BlockContent(text="a"), new="ab")


def test_undo_and_redo_stacks_are_per_task() -> None:
    history, _clock = _history()
    history.record(10, RemoveBlock(block_id=1))
    history.record(20, RemoveBlock(block_id=2))

    step = history.pop_undo(10)

    assert step is not None
    assert step.action == RemoveBlock(block_id=1)
    assert history.pop_undo(10) is None
    history.push_redo(10, InsertBlock(block=_block(1)))
    assert history.pop_redo(20) is None
    assert history.pop_redo(10) == InsertBlock(block=_block(1))
    assert history.pop_redo(10) is None
    assert history.push_undo(10, RemoveBlock(block_id=1)).action == RemoveBlock(block_id=1)


def _block(block_id: int) -> Block:
    return Block(
        id=block_id,
        task_id=10,
        type="key_idea",
        position=0,
        content=BlockContent(),
        phase="fill",
        created_at=WHEN,
        updated_at=WHEN,
    )


def test_take_insert_finds_the_delete_wherever_it_is() -> None:
    history, _clock = _history()
    history.record(10, InsertBlock(block=_block(1)))
    history.record(10, RemoveBlock(block_id=9))
    history.record(20, InsertBlock(block=_block(2)))

    step = history.take_insert(1)

    assert step is not None
    assert step.action == InsertBlock(block=_block(1))
    assert [s.action for s in history.undo[10]] == [RemoveBlock(block_id=9)]
    assert history.take_insert(1) is None


def test_load_replaces_everything() -> None:
    history, _clock = _history()
    history.record(10, RemoveBlock(block_id=1))
    history.push_redo(10, RemoveBlock(block_id=2))

    history.load([UndoEntry(id=5, room_id=1, task_id=30, action=RemoveBlock(block_id=3))])

    assert list(history.undo) == [30]
    assert history.undo[30][0].entry_id == 5
    assert history.redo == {}
