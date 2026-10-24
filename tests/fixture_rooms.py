"""Load the fixture rooms in tests/fixtures/rooms/.

The JSON mirrors the Phase 1 `app.db` tables from docs/BUILD_PLAN.md: a room
row with its tasks, each with its blocks. Field names match the columns, so
the Phase 1 migration tests can insert a fixture directly. If the schema
changes, change these models and the fixture files in the same pull request.

`_fixture` is test-only metadata: what each room deliberately contains, so
tests in later phases can check that mistakes are flagged, flags stripped and
concepts found. The app never sees it.
"""

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ROOMS_DIR = Path(__file__).resolve().parent / "fixtures" / "rooms"

BlockType = Literal[
    "key_idea", "command", "table", "screenshot", "question", "confused", "room_question", "voice"
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BlockContent(_Strict):
    """The `content` JSON column: text, plus per-type fields."""

    text: str = Field(min_length=1)
    answer: str | None = None
    """Room question blocks only."""


class Block(_Strict):
    """A row of `blocks`."""

    id: int
    type: BlockType
    position: int = Field(ge=0)
    content: BlockContent
    pass_: Literal["recall", "fill"] = Field(alias="pass")
    created_at: datetime
    updated_at: datetime


class Task(_Strict):
    """A row of `tasks`, with its blocks."""

    id: int
    task_index: int = Field(ge=1)
    title: str
    status: Literal["open", "done", "skipped"]
    blocks: list[Block]


class Mistake(_Strict):
    """A deliberate error, and the check that should catch it."""

    block_id: int
    claim: str
    correct: str
    check: Literal["conversions", "ports", "commands", "model"]


class FixtureMeta(_Strict):
    """What the room deliberately contains."""

    description: str
    mistakes: list[Mistake]
    flags: list[str]
    """Strings that must be stripped before storage (hard rule 2)."""
    flag_lookalikes: list[str]
    """Real content shaped like a flag (e.g. an example hash): stripped by default,
    restorable with "Not a flag, keep it"."""
    concepts: list[str] = Field(min_length=3)
    """Hand list of concepts the extraction should find (Phase 2 bake-off)."""
    tools: list[str]


class Room(_Strict):
    """A row of `rooms`, with its tasks and the fixture metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    id: int
    platform: str
    path: str
    module: str
    name: str
    task_count: int = Field(ge=1)
    mode: Literal["new", "from_memory"]
    status: Literal["capturing", "queued", "processing", "in_review", "done"]
    created_at: datetime
    updated_at: datetime
    time_spent_s: int = Field(ge=0)
    last_task_index: int = Field(ge=1)
    tasks: list[Task]
    fixture: FixtureMeta = Field(alias="_fixture")

    def block(self, block_id: int) -> Block:
        """Find a block anywhere in the room.

        Args:
            block_id: The block's id.

        Returns:
            The block.

        Raises:
            KeyError: No block has that id.
        """
        for task in self.tasks:
            for block in task.blocks:
                if block.id == block_id:
                    return block
        raise KeyError(block_id)


def load_room(path: Path) -> Room:
    """Parse and validate one fixture file."""
    return Room.model_validate_json(path.read_text(encoding="utf-8"))


def all_rooms() -> dict[str, Room]:
    """Every fixture room, keyed by file stem."""
    return {path.stem: load_room(path) for path in sorted(ROOMS_DIR.glob("*.json"))}
