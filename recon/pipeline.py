"""Processing one finished room, start to review (task 2.5). No Qt: the bridge runs it on a worker.

Three steps, each reported as one plain-English line (never a bare spinner):

1. "Reading your notes": the capture, from the database (`engine.capture`).
2. "Structuring 4 tasks with qwen3.5:9b": the model call (`engine.extract`).
3. "Preparing 12 notes for review": render and stage (`engine.notes`,
   `processing.stage_room`), which puts the room in review.

Linking, fact-checking and screenshots join in later phases. The room is
`processing` while this runs. A step that fails puts it back to `queued` with a
plain message, so Retry (or the next launch) runs it again. Cancelling between
steps leaves it `processing`, and the next launch picks it up again. Staging is
the last step and writes nothing to the vault, so stopping anywhere leaves nothing
half-written.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from recon.config import Settings
from recon.db.repositories import BlockRepository, RoomRepository, TaskRepository
from recon.engine.capture import Capture, capture_room
from recon.engine.extract import Model, extract
from recon.engine.notes import render_room
from recon.engine.stage import Manifest
from recon.errors import ReconError
from recon.logging_setup import Safe
from recon.processing import Processing

STEPS = 3

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Step:
    """Where a room's processing is, for the panel."""

    room: str
    number: int
    text: str


@dataclass(frozen=True, slots=True)
class Outcome:
    """How a run ended. Exactly one of `manifest`, `problem` or `cancelled` says so."""

    room: str
    manifest: Manifest | None = None
    problem: str = ""
    cancelled: bool = False


@dataclass(frozen=True, slots=True)
class Pipeline:
    """Everything a run needs, injected so tests can fake the model, clock and folders."""

    rooms: RoomRepository
    tasks: TaskRepository
    blocks: BlockRepository
    settings: Callable[[], Settings]
    processing_for: Callable[[Settings], Processing]
    """Where runs, backups and the vault are, for the settings in use."""
    model_for: Callable[[str], Model]
    """The Ollama service for an address (`services.ollama`)."""
    today: Callable[[], date] = date.today

    def run(
        self, room_id: int, report: Callable[[Step], None], cancelled: Callable[[], bool]
    ) -> Outcome:
        """Process one room into staged notes, reporting each step.

        Args:
            room_id: A room that's queued (or was cut off mid-run).
            report: Called at the start of each step.
            cancelled: Checked between steps; True stops the run.

        Returns:
            The outcome: the manifest for review, a problem to show, or cancelled.
        """
        room = self.rooms.get(room_id)
        if room is None or room.status not in {"queued", "processing"}:
            return Outcome(room=room.name if room else "", cancelled=True)
        name = room.name
        try:
            return self._steps(room_id, name, report, cancelled)
        except ReconError as exc:
            _log.warning("room %s not processed: %s", room_id, Safe(type(exc).__name__))
            self.rooms.update_progress(room_id, status="queued")
            return Outcome(room=name, problem=exc.user_message)

    def _steps(
        self,
        room_id: int,
        name: str,
        report: Callable[[Step], None],
        cancelled: Callable[[], bool],
    ) -> Outcome:
        self.rooms.update_progress(room_id, status="processing")
        report(Step(name, 1, "Reading your notes"))
        capture = self._capture(room_id)
        if cancelled():
            return Outcome(room=name, cancelled=True)
        settings = self.settings()
        processing = self.processing_for(settings)
        run = processing.runs.start()
        written = sum(1 for task in capture.tasks if task.blocks)
        tasks = f"{written} task" if written == 1 else f"{written} tasks"
        report(Step(name, 2, f"Structuring {tasks} with {settings.text_model}"))
        checked = extract(
            capture,
            self.model_for(settings.ollama_host),
            settings.text_model,
            run,
            think=settings.model_thinking,
        )
        rendered = render_room(capture, checked)
        if cancelled() or not self._still_processing(room_id):
            return Outcome(room=name, cancelled=True)
        report(Step(name, 3, f"Preparing {len(rendered.notes)} notes for review"))
        return Outcome(room=name, manifest=processing.stage_room(room_id, rendered, run))

    def _capture(self, room_id: int) -> Capture:
        room = self.rooms.get(room_id)
        if room is None:  # deleted mid-run: nothing to process
            raise ReconError
        tasks = [(task, self.blocks.for_task(task.id)) for task in self.tasks.for_room(room_id)]
        return capture_room(room, tasks, self.today())

    def _still_processing(self, room_id: int) -> bool:
        """False if the room was taken back ("Back to the room") while the model worked."""
        room = self.rooms.get(room_id)
        return room is not None and room.status == "processing"
