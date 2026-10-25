"""Rows of app.db as pydantic models: the boundary between the database and the rest of Recon."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type BlockType = Literal[
    "key_idea", "command", "table", "screenshot", "question", "confused", "room_question", "voice"
]
type BlockPass = Literal["recall", "fill"]
type TaskStatus = Literal["open", "done", "skipped"]
type RoomStatus = Literal["capturing", "queued", "processing", "in_review", "done"]
type RoomMode = Literal["new", "from_memory"]


class _Row(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class BlockContent(_Row):
    """The `content` JSON: text, plus fields some block types use.

    Text may be empty: a new block is saved before Tyler types into it.
    """

    text: str = ""
    answer: str | None = None
    """Room question blocks: the answer, kept hidden in the note."""


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
