"""Pipeline step 1, parse: the room as the user wrote it, ready for the model and templates.

Read straight from the app's rows: each block's type already says what it is
(a command, a table, a question), so nothing is guessed. Flags are stripped
once more here (hard rule 2), keeping only the hex strings the user marked "Not
a flag, keep it", so nothing flag-shaped reaches the model, the vault or a
run log. Empty blocks are left out. Screenshot blocks wait for the vision
step (Phase 5).
"""

from collections.abc import Sequence
from datetime import date
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from recon.db.models import Block, Room, Task
from recon.engine.flags_filter import strip_flags

type TextBlockType = Literal[
    "key_idea", "command", "table", "question", "confused", "room_question", "voice"
]
TEXT_TYPES: Final = frozenset(
    {"key_idea", "command", "table", "question", "confused", "room_question", "voice"}
)


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CaptureBlock(_Model):
    """One block's text, flags already removed."""

    id: int
    type: TextBlockType
    text: str
    answer: str = ""
    """A Room question's answer ("" for every other type)."""


class CaptureTask(_Model):
    """One task: its title, status and written blocks."""

    index: int
    title: str
    status: Literal["open", "done", "skipped"]
    blocks: tuple[CaptureBlock, ...]


class Capture(_Model):
    """A finished room, as the pipeline reads it."""

    room_id: int
    name: str
    platform: str
    path: str
    module: str
    finished_on: date
    time_spent_s: int
    tasks: tuple[CaptureTask, ...]

    def blocks(self) -> tuple[CaptureBlock, ...]:
        """Every block in the room, in order."""
        return tuple(block for task in self.tasks for block in task.blocks)

    def block(self, block_id: int) -> CaptureBlock | None:
        """The block with this ID, if the room has it."""
        return next((b for b in self.blocks() if b.id == block_id), None)


def capture_room(
    room: Room, tasks: Sequence[tuple[Task, Sequence[Block]]], finished_on: date
) -> Capture:
    """Build the capture from the room's rows.

    Args:
        room: The room.
        tasks: Each task with its blocks, in order.
        finished_on: The day it was finished (the user's local date).

    Returns:
        The capture, flags stripped and empty blocks left out.
    """
    return Capture(
        room_id=room.id,
        name=_clean(room.name),
        platform=_clean(room.platform),
        path=_clean(room.path),
        module=_clean(room.module),
        finished_on=finished_on,
        time_spent_s=room.time_spent_s,
        tasks=tuple(
            CaptureTask(
                index=task.task_index,
                title=_clean(task.title),
                status=task.status,
                blocks=tuple(b for b in (_block(block) for block in blocks) if b is not None),
            )
            for task, blocks in tasks
        ),
    )


def _block(block: Block) -> CaptureBlock | None:
    if block.type not in TEXT_TYPES:
        return None
    kept = block.content.kept
    text = _clean(block.content.text, kept)
    answer = _clean(block.content.answer or "", kept) if block.type == "room_question" else ""
    if not (text.strip() or answer.strip()):
        return None
    return CaptureBlock.model_validate(
        {"id": block.id, "type": block.type, "text": text, "answer": answer}
    )


def _clean(text: str, kept: tuple[str, ...] = ()) -> str:
    return strip_flags(text, kept, unfinished=True).text.strip("\n")
