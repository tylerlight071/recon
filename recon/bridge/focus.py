"""The header's timer, exposed to QML as `Focus` (task 1.12).

- **Time on task**, shown quietly in the chip and recorded per task and room.
  It counts while the user is working: any edit in Recon keeps it going, and it
  carries on for up to 15 minutes without one (the user is reading the room
  in the browser). After that they're away, and it stops until they're back.
- **Focus blocks** of 15, 25 or 45 minutes, chosen from the chip. The chip
  shows a thin line filling up, never a countdown (ADHD rule 10). At the end:
  a gentle notice, and the soft chime if it's on in Settings (off by default).
- **A break nudge** after 90 minutes of continuous work: one gentle toast.
  A pause of 15 minutes counts as the break, so the next one starts fresh.
"""

import logging
import time
from collections.abc import Callable
from typing import Final

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from recon.bridge.workers import Submit
from recon.db.models import Task
from recon.db.repositories import TaskRepository
from recon.errors import ReconError
from recon.logging_setup import Safe

AWAY_AFTER_S: Final = 15 * 60
"""No edit in Recon for this long: The user is away, so time stops counting."""
BREAK_AFTER_S: Final = 90 * 60
SAVE_EVERY_S: Final = 30
"""Time on task is written this often (and on every task switch and at quit)."""
FOCUS_PRESETS: Final = (15, 25, 45)
TICK_MS: Final = 1000
MAX_TICK_S: Final = 2.0
"""A longer gap between ticks (a suspend, a stall) counts as this much, not all of it."""

_log = logging.getLogger(__name__)


class FocusBridge(QObject):
    """Counts time on task, runs focus blocks and suggests a break."""

    changed = Signal()
    focusDone = Signal(int)  # noqa: N815 - Qt naming; the block's length in minutes
    breakSuggested = Signal()  # noqa: N815 - Qt naming, used from QML

    def __init__(  # noqa: PLR0913 - every collaborator is injected (CLAUDE.md)
        self,
        tasks: TaskRepository,
        chime: Callable[[], None],
        chime_on: Callable[[], bool],
        *,
        submit: Submit,
        monotonic: Callable[[], float] = time.monotonic,
        parent: QObject | None = None,
    ) -> None:
        """Wire the timer.

        Args:
            tasks: Records time per task (and its room).
            chime: Plays the chime.
            chime_on: Whether Settings has the chime on (read at the moment it's due).
            submit: Runs a save off the UI thread.
            monotonic: Seconds.
            parent: Qt parent.
        """
        super().__init__(parent)
        self._tasks = tasks
        self._chime = chime
        self._chime_on = chime_on
        self._submit = submit
        self._monotonic = monotonic
        now = monotonic()
        self._task_id: int | None = None
        self._seen: dict[int, float] = {}
        self._shown = 0.0
        self._unsaved = 0.0
        self._streak = 0.0
        self._nudged = False
        self._last_tick = now
        self._last_activity = now
        self._running = False
        self._focus_minutes = 0
        self._focus_started = 0.0
        self._timer = QTimer(self, interval=TICK_MS)
        self._timer.timeout.connect(self.tick)

    # ---- Properties ------------------------------------------------------------------

    def _seconds(self) -> int:
        return int(self._shown)

    def _get_running(self) -> bool:
        return self._running

    def _focusing(self) -> bool:
        return self._focus_minutes > 0

    def _focus_progress(self) -> float:
        if not self._focus_minutes:
            return 0.0
        done = (self._monotonic() - self._focus_started) / (self._focus_minutes * 60)
        return max(0.0, min(1.0, done))

    def _get_focus_minutes(self) -> int:
        return self._focus_minutes

    def _presets(self) -> list[int]:
        return list(FOCUS_PRESETS)

    seconds = Property(int, _seconds, notify=changed)
    """Time on the task on screen, in whole seconds."""
    running = Property(bool, _get_running, notify=changed)
    """Counting now (False while the user is away)."""
    focusing = Property(bool, _focusing, notify=changed)
    focusMinutes = Property(int, _get_focus_minutes, notify=changed)  # noqa: N815
    focusProgress = Property(float, _focus_progress, notify=changed)  # noqa: N815
    presets = Property(list, _presets, constant=True)

    # ---- Tasks and activity -----------------------------------------------------------

    def set_task(self, task: Task | None) -> None:
        """A task was opened (or the room closed): save the last task's time, show this one's."""
        self._save()
        if self._task_id is not None:
            self._seen[self._task_id] = self._shown
        self._task_id = task.id if task else None
        # The last save may not have landed when the task was read back: take the larger.
        self._shown = max(float(task.time_spent_s), self._seen.get(task.id, 0.0)) if task else 0.0
        self.activity()
        if task is None:
            self._timer.stop()
        elif not self._timer.isActive():
            self._last_tick = self._monotonic()
            self._timer.start()
        self.changed.emit()

    @Slot()
    def activity(self) -> None:
        """The user did something in Recon: they're here."""
        self._last_activity = self._monotonic()

    @Slot()
    def tick(self) -> None:
        """Once a second: count, save now and then, and check the focus block and break."""
        now = self._monotonic()
        delta = max(0.0, min(now - self._last_tick, MAX_TICK_S))
        self._last_tick = now
        if self._task_id is not None:
            self._count(now, delta)
        if self._focus_minutes and now - self._focus_started >= self._focus_minutes * 60:
            self._finish_focus()
        self.changed.emit()

    def _count(self, now: float, delta: float) -> None:
        self._running = now - self._last_activity <= AWAY_AFTER_S
        if not self._running:
            # A long pause is the break: the next stretch starts from zero.
            self._streak = 0.0
            self._nudged = False
            return
        self._shown += delta
        self._unsaved += delta
        self._streak += delta
        if self._streak >= BREAK_AFTER_S and not self._nudged:
            self._nudged = True
            self.breakSuggested.emit()
        if self._unsaved >= SAVE_EVERY_S:
            self._save()

    # ---- Focus blocks -----------------------------------------------------------------

    @Slot(int)
    def startFocus(self, minutes: int) -> None:  # noqa: N802 - Qt naming, used from QML
        """Start a 15, 25 or 45 minute focus block (others are ignored)."""
        if minutes not in FOCUS_PRESETS:
            return
        self._focus_minutes = minutes
        self._focus_started = self._monotonic()
        self.activity()
        self.changed.emit()

    @Slot()
    def stopFocus(self) -> None:  # noqa: N802 - Qt naming, used from QML
        """Stop the focus block early (always fine)."""
        self._focus_minutes = 0
        self.changed.emit()

    @Slot()
    def previewChime(self) -> None:  # noqa: N802 - Qt naming, used from QML
        """Settings' "Play": let the user hear the chime before turning it on."""
        self._chime()

    def _finish_focus(self) -> None:
        minutes, self._focus_minutes = self._focus_minutes, 0
        if self._chime_on():
            self._chime()
        self.focusDone.emit(minutes)

    # ---- Saving -------------------------------------------------------------------------

    def _save(self) -> None:
        seconds, task_id = int(self._unsaved), self._task_id
        if seconds <= 0 or task_id is None:
            return
        self._unsaved -= seconds

        def job() -> None:
            # Thread boundary. Time on task is nice to have: a failed save is logged, not shown.
            try:
                self._tasks.add_time(task_id, seconds)
            except Exception as exc:  # thread boundary: log the type, never the panel's problem
                _log.warning("time on task not saved: %s", Safe(type(exc).__name__))

        self._submit(job)

    def close(self) -> None:
        """At quit: save the time not yet written, now."""
        seconds, task_id = int(self._unsaved), self._task_id
        self._unsaved = 0.0
        self._timer.stop()
        if seconds > 0 and task_id is not None:
            try:
                self._tasks.add_time(task_id, seconds)
            except ReconError as exc:
                _log.warning("time on task not saved at quit: %s", Safe(type(exc).__name__))
