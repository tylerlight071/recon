"""The done screen, exposed to QML as `DoneModel` (task 2.7; `Done` is the screen's own name).

After Apply: a short completion moment, the room's place in its path ("3 rooms
done in Pre Security."), and "Open in Obsidian" for the room note. Obsidian
only follows links to vaults it knows, so until the user has confirmed opening
the vault once, the screen shows that one-time step instead (`Vault`). If a
link still doesn't open, "Didn't open?" brings that step back rather than
showing an error (task 2.1). Flashcards (Phase 4) will come between Apply and
this screen.
"""

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from recon.bridge.workers import Submit
from recon.db.repositories import RoomRepository
from recon.engine.notes import room_note_path
from recon.errors import ReconError
from recon.logging_setup import Safe

type Then = Callable[[], None]
type OpenNote = Callable[[Path], bool]

_log = logging.getLogger(__name__)


def progress_line(done: int, path: str) -> str:
    """The room's place in its path, kindly: never a target, only what's done."""
    if not path:
        return "1 room done so far." if done == 1 else f"{done} rooms done so far."
    if done == 1:
        return f"Your first room in {path}."
    return f"{done} rooms done in {path}."


class DoneBridge(QObject):
    """The finished room, and the way to read it in Obsidian."""

    changed = Signal()
    opened = Signal()
    _done = Signal(object)

    def __init__(  # noqa: PLR0913 - every collaborator is injected (CLAUDE.md)
        self,
        rooms: RoomRepository,
        vault: Callable[[], Path],
        open_note: OpenNote,
        forget_opened: Callable[[], None],
        *,
        submit: Submit,
        parent: QObject | None = None,
    ) -> None:
        """Wire the done screen.

        Args:
            rooms: Room names, paths and how many are done.
            vault: The vault folder in use.
            open_note: Opens a note in Obsidian (`services.open_url.open_in_obsidian`).
            forget_opened: Shows the "open your vault in Obsidian once" step again.
            submit: Runs reads off the UI thread.
            parent: Qt parent.
        """
        super().__init__(parent)
        self._rooms = rooms
        self._vault = vault
        self._open_note = open_note
        self._forget_opened = forget_opened
        self._submit = submit
        self._room_name = ""
        self._written = 0
        self._progress = ""
        self._note: Path | None = None
        self._problem = ""
        self._tried = False
        self._done.connect(lambda then: then())

    # ---- Properties --------------------------------------------------------------------

    def _get_room_name(self) -> str:
        return self._room_name

    def _get_written(self) -> int:
        return self._written

    def _get_progress(self) -> str:
        return self._progress

    def _get_problem(self) -> str:
        return self._problem

    def _get_tried(self) -> bool:
        return self._tried

    roomName = Property(str, _get_room_name, notify=changed)  # noqa: N815
    written = Property(int, _get_written, notify=changed)
    """Notes this Apply wrote (0 when the screen is reopened later from Home)."""
    progress = Property(str, _get_progress, notify=changed)
    problem = Property(str, _get_problem, notify=changed)
    tried = Property(bool, _get_tried, notify=changed)
    """"Open in Obsidian" was pressed: offer "Didn't open?"."""

    # ---- Actions -----------------------------------------------------------------------

    def show(self, room_id: int, written: int = 0) -> None:
        """Show a room that's in the vault (just applied, or opened again from Home)."""

        def job() -> None:
            # Thread boundary: a failed read still shows the screen, without the extras.
            try:
                room = self._rooms.get(room_id)
                if room is None:
                    return
                progress = progress_line(self._rooms.done_in_path(room.path), room.path)
                note = self._vault() / room_note_path(room.platform, room.path, room.name)
            except ReconError as exc:
                _log.warning("done screen not loaded: %s", Safe(type(exc).__name__))
                return
            self._done.emit(lambda: self._set(room.name, written, progress, note))

        self._submit(job)

    def _set(self, name: str, written: int, progress: str, note: Path) -> None:
        self._room_name, self._written, self._progress, self._note = name, written, progress, note
        self._problem, self._tried = "", False
        self.changed.emit()
        self.opened.emit()

    @Slot()
    def openInObsidian(self) -> None:  # noqa: N802 - Qt naming, used from QML
        """Open the room note in Obsidian."""
        if self._note is None:
            return
        self._tried = True
        opened = self._open_note(self._note)
        self._problem = (
            ""
            if opened
            else "Couldn't open Obsidian. Is it installed? Your note is in the vault either way."
        )
        _log.info("open in obsidian: %s", Safe("handed over" if opened else "not opened"))
        self.changed.emit()

    @Slot()
    def notOpened(self) -> None:  # noqa: N802 - Qt naming, used from QML
        """The link didn't open the note: show the one-time Obsidian step again."""
        self._tried = False
        self._forget_opened()
        self.changed.emit()
