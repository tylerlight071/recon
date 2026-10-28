"""Fixture rooms as pipeline input, and recorded model replies (no GPU needed).

`capture_of("number_systems")` builds step 1's capture from a fixture room
exactly as the app would from its rows. `recorded("number_systems")` is the
extract reply captured from the real model by `scripts/record_responses.py`.
"""

from datetime import date
from pathlib import Path

from recon.db.models import Block, BlockContent, Room, Task
from recon.engine.capture import Capture, capture_room
from recon.engine.schemas import RoomExtract
from tests.fixture_rooms import all_rooms

RESPONSES = Path(__file__).resolve().parents[1] / "fixtures" / "responses"
FINISHED = date(2026, 10, 28)


def rows_of(name: str) -> tuple[Room, list[tuple[Task, list[Block]]]]:
    """A fixture room as the database's rows."""
    fixture = all_rooms()[name]
    room = Room.model_validate(fixture.model_dump(exclude={"tasks", "fixture"}))
    tasks = [
        (
            Task(
                id=task.id,
                room_id=fixture.id,
                task_index=task.task_index,
                title=task.title,
                status=task.status,
            ),
            [
                Block.model_validate(
                    {
                        **block.model_dump(by_alias=True, exclude={"content"}),
                        "task_id": task.id,
                        "content": BlockContent(
                            text=block.content.text, answer=block.content.answer
                        ),
                    }
                )
                for block in task.blocks
            ],
        )
        for task in fixture.tasks
    ]
    return room, tasks


def capture_of(name: str) -> Capture:
    """Step 1's capture of a fixture room."""
    room, tasks = rows_of(name)
    return capture_room(room, tasks, FINISHED)


def recorded(name: str) -> RoomExtract:
    """The real model's extract reply for a fixture room, as recorded."""
    return RoomExtract.model_validate_json((RESPONSES / f"{name}.extract.json").read_text())
