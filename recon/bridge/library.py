"""Library (task 2.8, first pass), exposed to QML as `LibraryModel`.

- **Rooms:** every room in the vault, newest first, with its path and date and
  "Open in Obsidian" for its note.
- **History:** every Apply, newest first: how many notes it wrote and backed
  up, with one-click Restore. Restore puts back the versions that Apply
  replaced. It first backs up what's there now, as a History entry of its own,
  so a restore can be undone by restoring that entry; the toast's Undo does
  exactly that. Notes a run created are left in place.

Concepts, tools and open flags join the Library in later phases.
"""

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from recon.bridge.workers import Submit
from recon.db.models import HistoryEntry, Room, Run
from recon.engine.notes import room_note_path
from recon.errors import ReconError
from recon.logging_setup import Safe

type Then = Callable[[], None]
type Load = Callable[[], tuple[list[Room], list[HistoryEntry]]]
"""Rooms in the vault, and History, read off the UI thread."""

_log = logging.getLogger(__name__)


def day(when: datetime) -> str:
    """A date as people say it: "28 October 2026" (local time)."""
    local = when.astimezone()
    return f"{local.day} {local:%B %Y}"


def history_detail(run: Run) -> str:
    """What a History entry did, in plain words."""
    notes = f"{run.written} note{'' if run.written == 1 else 's'}"
    if run.restored_from:
        return f"Restored {notes}"
    if run.backed_up:
        return f"{notes} written, {run.backed_up} replaced"
    return f"{notes} written"


class LibraryBridge(QObject):
    """Rooms in the vault and the History of runs."""

    changed = Signal()
    restored = Signal(str, str)
    _done = Signal(object)

    def __init__(  # noqa: PLR0913 - every collaborator is injected (CLAUDE.md)
        self,
        load: Load,
        restore: Callable[[str], Run],
        vault: Callable[[], Path],
        open_note: Callable[[Path], bool],
        *,
        submit: Submit,
        parent: QObject | None = None,
    ) -> None:
        """Wire the Library.

        Args:
            load: Rooms in the vault and History.
            restore: Restores a run's backup; returns the new (restore) run.
            vault: The vault folder in use.
            open_note: Opens a note in Obsidian.
            submit: Runs reads and restores off the UI thread, in order.
            parent: Qt parent.
        """
        super().__init__(parent)
        self._load, self._restore = load, restore
        self._vault, self._open_note = vault, open_note
        self._submit = submit
        self._rooms: list[Room] = []
        self._history: list[HistoryEntry] = []
        self._busy = False
        self._problem = ""
        self._done.connect(lambda then: then())

    # ---- Properties --------------------------------------------------------------------

    def _room_rows(self) -> list[dict[str, object]]:
        return [
            {
                "id": room.id,
                "name": room.name,
                "detail": " · ".join(p for p in (room.path, room.module) if p),
                "date": day(room.updated_at),
            }
            for room in self._rooms
        ]

    def _history_rows(self) -> list[dict[str, object]]:
        return [
            {
                "runId": entry.run.id,
                "room": entry.room_name,
                "detail": history_detail(entry.run),
                "date": day(entry.run.finished_at or entry.run.created_at),
                "canRestore": entry.run.backed_up > 0,
            }
            for entry in self._history
        ]

    def _get_busy(self) -> bool:
        return self._busy

    def _get_problem(self) -> str:
        return self._problem

    rooms = Property(list, _room_rows, notify=changed)
    history = Property(list, _history_rows, notify=changed)
    busy = Property(bool, _get_busy, notify=changed)
    problem = Property(str, _get_problem, notify=changed)

    # ---- Actions -----------------------------------------------------------------------

    @Slot()
    def refresh(self) -> None:
        """Read the rooms and History again."""

        def work() -> Then:
            rooms, history = self._load()
            return lambda: self._set(rooms, history)

        self._background(work)

    def _set(self, rooms: list[Room], history: list[HistoryEntry]) -> None:
        self._rooms, self._history = rooms, history
        self.changed.emit()

    @Slot(int)
    def openRoom(self, room_id: int) -> None:  # noqa: N802 - Qt naming, used from QML
        """Open a room's note in Obsidian."""
        room = next((r for r in self._rooms if r.id == room_id), None)
        if room is None:
            return
        note = self._vault() / room_note_path(room.platform, room.path, room.name)
        opened = self._open_note(note)
        self._problem = (
            ""
            if opened
            else f"Couldn't open {room.name} in Obsidian. "
            "Is the note still in your vault, and is Obsidian installed?"
        )
        self.changed.emit()

    @Slot(str)
    def restore(self, run_id: str) -> None:
        """Put back what a run replaced (and back up what's there now, for Undo)."""
        entry = next((e for e in self._history if e.run.id == run_id), None)
        if entry is None or self._busy:
            return

        def work() -> Then:
            new = self._restore(run_id)
            rooms, history = self._load()
            notes = f"{new.written} note{'' if new.written == 1 else 's'}"
            message = f"Restored {notes} in {entry.room_name} to how they were."

            def then() -> None:
                self._set(rooms, history)
                self.restored.emit(message, new.id)

            return then

        self._background(work)

    # ---- Background jobs ----------------------------------------------------------------

    def _background(self, work: Callable[[], Then]) -> None:
        self._busy, self._problem = True, ""
        self.changed.emit()

        def job() -> None:
            # Thread boundary: a calm line on the screen, never a stuck Library.
            try:
                then = work()
            except ReconError as exc:
                _log.warning("library step failed: %s", Safe(type(exc).__name__))
                message = exc.user_message
                then = lambda: self._show_problem(message)  # noqa: E731 - one-line callback
            except Exception as exc:  # thread boundary
                _log.error("library step failed: %s", Safe(type(exc).__name__))
                then = lambda: self._show_problem(ReconError.user_message)  # noqa: E731
            self._done.emit(lambda: self._idle(then))

        self._submit(job)

    def _show_problem(self, message: str) -> None:
        self._problem = message

    def _idle(self, then: Then) -> None:
        self._busy = False
        then()
        self.changed.emit()
