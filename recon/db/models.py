"""Rows of app.db as pydantic models: the boundary between the database and the rest of Recon."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

type BlockType = Literal[
    "key_idea", "command", "table", "screenshot", "question", "confused", "room_question", "voice"
]
type BlockPass = Literal["recall", "fill"]
type TaskStatus = Literal["open", "done", "skipped"]
type RoomStatus = Literal["capturing", "queued", "processing", "in_review", "done"]
type RoomMode = Literal["new", "from_memory"]
type RunStatus = Literal["staged", "applied", "discarded"]


class _Row(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class BlockContent(_Row):
    """The `content` JSON: text, plus fields some block types use.

    Text may be empty: a new block is saved before the user types into it.
    """

    text: str = ""
    answer: str | None = None
    """Room question blocks: the answer, kept hidden in the note."""
    kept: tuple[str, ...] = ()
    """Hex strings the user marked "Not a flag, keep it" (hard rule 2's one exception)."""


class NewRoom(_Row):
    """What Start a room collects (task 1.8)."""

    platform: str = "TryHackMe"
    path: str = ""
    module: str = ""
    name: str = Field(min_length=1)
    task_count: int = Field(ge=1)
    mode: RoomMode = "new"


class Room(_Row):
    """A row of `rooms`."""

    id: int
    platform: str
    path: str
    module: str
    name: str
    task_count: int
    mode: RoomMode
    status: RoomStatus
    created_at: datetime
    updated_at: datetime
    time_spent_s: int
    last_task_index: int


class Task(_Row):
    """A row of `tasks`."""

    id: int
    room_id: int
    task_index: int
    title: str
    status: TaskStatus
    time_spent_s: int = 0


class Block(_Row):
    """A row of `blocks`."""

    id: int
    task_id: int
    type: BlockType
    position: int
    content: BlockContent
    phase: BlockPass = Field(alias="pass")
    """Column `pass`: "recall" in From memory's first pass, otherwise "fill"."""
    created_at: datetime
    updated_at: datetime


# ---- Undo (task 1.11) ------------------------------------------------------------
# Each entry in `undo_log` is the action that puts things back. Applying one
# returns its opposite, which goes on the other stack (undo <-> redo).


class SetContent(_Row):
    """Put a block's content back as it was."""

    kind: Literal["set_content"] = "set_content"
    block_id: int
    content: BlockContent


class RemoveBlock(_Row):
    """Remove a block (undoing an add)."""

    kind: Literal["remove_block"] = "remove_block"
    block_id: int


class InsertBlock(_Row):
    """Put a deleted block back, at its old place."""

    kind: Literal["insert_block"] = "insert_block"
    block: Block


class MoveBlock(_Row):
    """Move a block back to where it was."""

    kind: Literal["move_block"] = "move_block"
    block_id: int
    position: int


type UndoAction = Annotated[
    SetContent | RemoveBlock | InsertBlock | MoveBlock, Field(discriminator="kind")
]


def action_block_id(action: UndoAction) -> int:
    """The block an undo action is about."""
    return action.block.id if isinstance(action, InsertBlock) else action.block_id


class UndoEntry(_Row):
    """A row of `undo_log`: one step back for a task."""

    id: int
    room_id: int
    task_id: int
    action: UndoAction


# ---- Processing runs (task 2.4) ---------------------------------------------------


class Run(_Row):
    """A row of `runs`: one processing of a room, from staging to Apply or Discard."""

    id: str
    room_id: int
    status: RunStatus
    created_at: datetime
    finished_at: datetime | None
    written: int
    """Vault files Apply wrote."""
    backed_up: int
    """Files Apply copied to `backups/<run id>/` before overwriting them."""
    restored_from: str | None = None
    """For a restore from History: the run whose backup was put back."""


class HistoryEntry(_Row):
    """An applied run in Library's History, with its room's name."""

    run: Run
    room_name: str
