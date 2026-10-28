"""Background processing, exposed to QML as `Processing` (task 2.5).

Finishing a room queues it here. One room processes at a time (hard rule 10),
on a daemon worker, so the app stays usable and quitting never waits for the
model. The panel shows the room it's looking at (`show`): the step in plain
English, "Waiting…" behind another room, "Ready to review", or what went wrong
with a Retry. When a room is ready, or can't be processed, a desktop
notification says so, and clicking it opens that room (`reviewRequested`).

At launch, `resume` queues every room left queued or cut off mid-run, oldest first.
"""

import logging
from collections.abc import Callable
from typing import Final, Protocol

from PySide6.QtCore import Property, QObject, Signal, Slot

from recon.bridge.workers import Submit
from recon.db.models import Room
from recon.errors import ReconError
from recon.logging_setup import Safe
from recon.pipeline import STEPS, Outcome, Step
from recon.services.notifications import Notice

WAITING_TEXT: Final = "Waiting while another room is processed."
READY_ACTIONS: Final = (("default", "Review"),)
PROBLEM_ACTIONS: Final = (("default", "Open Recon"),)

_log = logging.getLogger(__name__)


class Runner(Protocol):
    """Runs a room through the pipeline (`pipeline.Pipeline.run`)."""

    def run(
        self, room_id: int, report: Callable[[Step], None], cancelled: Callable[[], bool]
    ) -> Outcome:
        """Process one room."""


type Notify = Callable[[Notice], None]
type Waiting = Callable[[], list[Room]]


class ProcessingBridge(QObject):
    """The processing queue, its progress for the panel, and its notifications."""

    changed = Signal()
    readyForReview = Signal(int)  # noqa: N815 - Qt naming; the room ID
    reviewRequested = Signal(int)  # noqa: N815 - Qt naming; a notification was clicked
    _stepped = Signal(int, object)
    _ended = Signal(int, object)
    _found = Signal(object)
    _clicked = Signal(int)

    def __init__(
        self,
        runner: Runner,
        notify: Notify,
        waiting: Waiting,
        *,
        submit: Submit,
        parent: QObject | None = None,
    ) -> None:
        """Wire the queue.

        Args:
            runner: Processes one room (on the worker).
            notify: Sends a desktop notification.
            waiting: Rooms left queued or mid-run (read on the worker at launch).
            submit: The processing worker: one job at a time, in order.
            parent: Qt parent.
        """
        super().__init__(parent)
        self._runner = runner
        self._notify = notify
        self._waiting_rooms = waiting
        self._submit = submit
        self._queue: list[int] = []
        self._running: int | None = None
        self._steps: dict[int, Step] = {}
        self._problems: dict[int, str] = {}
        self._ready: dict[int, int] = {}
        self._withdrawn: set[int] = set()
        self._stopping = False
        self._shown = 0
        self._stepped.connect(self._on_step)
        self._ended.connect(self._on_end)
        self._found.connect(self._on_found)
        self._clicked.connect(self.reviewRequested)

    # ---- Properties: the room the panel shows -------------------------------------------

    def _line(self) -> str:
        room = self._shown
        if room in self._problems:
            return self._problems[room]
        if room == self._running and room in self._steps:
            return self._steps[room].text
        if room in self._queue:
            return WAITING_TEXT if self._running not in {None, room} else "Starting…"
        if room in self._ready:
            count = self._ready[room]
            return f"Ready to review: {count} note{'' if count == 1 else 's'}."
        return ""

    def _step_number(self) -> int:
        step = self._steps.get(self._shown)
        return step.number if step and self._shown == self._running else 0

    def _busy(self) -> bool:
        return self._shown != 0 and self._shown == self._running

    def _failed(self) -> bool:
        return self._shown in self._problems

    def _steps_total(self) -> int:
        return STEPS

    def _queued_count(self) -> int:
        return len(self._queue)

    line = Property(str, _line, notify=changed)
    """One plain line about the shown room ("" if processing has nothing to say)."""
    stepNumber = Property(int, _step_number, notify=changed)  # noqa: N815
    steps = Property(int, _steps_total, constant=True)
    busy = Property(bool, _busy, notify=changed)
    """The shown room is processing right now."""
    failed = Property(bool, _failed, notify=changed)
    """The shown room couldn't be processed: show Retry."""
    queued = Property(int, _queued_count, notify=changed)
    """Rooms waiting or processing."""

    # ---- Queue -----------------------------------------------------------------------------

    def enqueue(self, room_id: int) -> None:
        """Process a finished room (after any already waiting)."""
        if room_id in self._queue:
            return
        self._withdrawn.discard(room_id)
        self._problems.pop(room_id, None)
        self._ready.pop(room_id, None)
        self._queue.append(room_id)
        self.changed.emit()
        self._submit(lambda: self._process(room_id))

    def withdraw(self, room_id: int) -> None:
        """The room went back to capturing: drop it from the queue, or stop it between steps."""
        self._withdrawn.add(room_id)
        self._problems.pop(room_id, None)
        self._ready.pop(room_id, None)
        if room_id in self._queue and room_id != self._running:
            self._queue.remove(room_id)
        self.changed.emit()

    def show(self, room_id: int) -> None:
        """Say which room the panel is showing (0 for none)."""
        self._shown = room_id
        self.changed.emit()

    @Slot()
    def retry(self) -> None:
        """Try the shown room again after a problem."""
        if self._shown in self._problems:
            self.enqueue(self._shown)

    def resume(self) -> None:
        """At launch: queue every room left queued or cut off mid-run."""

        def job() -> None:
            # Thread boundary: a failed read leaves those rooms for the next launch.
            try:
                ids = [room.id for room in self._waiting_rooms()]
            except ReconError as exc:
                _log.warning("waiting rooms not read: %s", Safe(type(exc).__name__))
                return
            self._found.emit(ids)

        self._submit(job)

    def close(self) -> None:
        """At quit: stop between steps; the room stays queued for next time."""
        self._stopping = True

    def action(self, room_id: int, _key: str) -> None:
        """A notification was clicked (called on the notification thread)."""
        self._clicked.emit(room_id)

    # ---- On the worker ------------------------------------------------------------------------

    def _process(self, room_id: int) -> None:
        if room_id in self._withdrawn or self._stopping:
            self._ended.emit(room_id, Outcome(room="", cancelled=True))
            return

        def cancelled() -> bool:
            return self._stopping or room_id in self._withdrawn

        # Thread boundary: whatever happens, the queue moves on and the panel hears why.
        try:
            outcome = self._runner.run(
                room_id, lambda step: self._stepped.emit(room_id, step), cancelled
            )
        except Exception as exc:  # thread boundary
            _log.error("processing failed: %s", Safe(type(exc).__name__))
            outcome = Outcome(room="", problem=ReconError.user_message)
        self._ended.emit(room_id, outcome)

    # ---- Back on the UI thread -----------------------------------------------------------------

    def _on_step(self, room_id: int, step: Step) -> None:
        self._running = room_id
        self._steps[room_id] = step
        self.changed.emit()

    def _on_end(self, room_id: int, outcome: Outcome) -> None:
        if room_id in self._queue:
            self._queue.remove(room_id)
        if self._running == room_id:
            self._running = None
        self._steps.pop(room_id, None)
        if outcome.manifest is not None:
            self._ready[room_id] = len(outcome.manifest.files)
            self._notify(
                Notice(
                    room_id,
                    f"{outcome.room} is ready to review",
                    "Your notes are ready. Check them over, then Apply.",
                    READY_ACTIONS,
                )
            )
            self.readyForReview.emit(room_id)
        elif outcome.problem and room_id not in self._withdrawn:
            self._problems[room_id] = outcome.problem
            name = outcome.room or "A room"
            self._notify(
                Notice(room_id, f"{name} couldn't be processed", outcome.problem, PROBLEM_ACTIONS)
            )
        self.changed.emit()

    def _on_found(self, ids: list[int]) -> None:
        for room_id in ids:
            self.enqueue(room_id)
