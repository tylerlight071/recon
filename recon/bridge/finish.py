"""Finishing a room, exposed to QML as `Finish` (task 1.13; queues processing since 2.5).

"Finish room" queues the room for processing (`processRequested`) and shows a
calm completion moment in the panel: what was written, how long it took, how
processing is going, and "Export as Markdown" (one `.md` per room, into a
folder the user picks; the folder is remembered). Task 2.7 adds the review
and Apply steps. "Back to the room" undoes the finish, discarding anything
staged, so pressing it by mistake costs nothing.
"""

import logging
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Final

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from recon.bridge.settings import SettingsBridge
from recon.bridge.workers import Submit
from recon.db.models import Room, Task
from recon.db.repositories import (
    BlockRepository,
    RoomRepository,
    TaskRepository,
    UndoRepository,
)
from recon.engine.export import export_room
from recon.engine.render import ExportBlock, ExportRoom, ExportTask, duration
from recon.errors import ReconError
from recon.logging_setup import Safe

type Then = Callable[[], None]

_STATUS_LINES: Final = {
    "queued": "Waiting to be processed.",
    "processing": "Waiting to be processed.",
    "in_review": "Ready to review.",
}

_log = logging.getLogger(__name__)


def summary(tasks: list[Task]) -> str:
    """What was done, kindly: "All 7 tasks written up." or "7 tasks: 6 written up, 1 skipped."."""
    skipped = sum(task.status == "skipped" for task in tasks)
    total = len(tasks)
    noun = "task" if total == 1 else "tasks"
    if not skipped:
        return f"All {total} {noun} written up." if total > 1 else f"{total} {noun} written up."
    return f"{total} {noun}: {total - skipped} written up, {skipped} skipped."


def shown_path(path: Path, home: Path) -> str:
    """A path as the user would say it: under the home folder it starts with ~."""
    return f"~/{path.relative_to(home)}" if path.is_relative_to(home) else str(path)


class FinishBridge(QObject):
    """The Finish screen in the panel: mark done, export, go back or close."""

    changed = Signal()
    reopenRequested = Signal(int)  # noqa: N815 - Qt naming; the room ID ("Back to the room")
    processRequested = Signal(int)  # noqa: N815 - Qt naming; the room ID (finished: process it)
    closed = Signal()
    failed = Signal(str)
    _done = Signal(object)

    def __init__(  # noqa: PLR0913 - every collaborator is injected (CLAUDE.md)
        self,
        repos: tuple[RoomRepository, TaskRepository, BlockRepository, UndoRepository],
        settings: SettingsBridge,
        open_folder: Callable[[Path], bool],
        *,
        submit: Submit,
        discard_staged: Callable[[int], int] = lambda _room: 0,
        today: Callable[[], date] = date.today,
        home: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Wire Finish to storage, settings and the file manager.

        Args:
            repos: Rooms, tasks, blocks and the undo log.
            settings: Remembers the export folder.
            open_folder: Shows a folder in the file manager.
            submit: Runs a job off the UI thread, in order with the session's.
            discard_staged: Throws away a room's staged notes ("Back to the room").
            today: The date written on the export.
            home: The user's home folder, for showing paths as ~/… (defaults to Path.home()).
            parent: Qt parent.
        """
        super().__init__(parent)
        self._rooms, self._tasks, self._blocks, self._undo = repos
        self._settings = settings
        self._open_folder = open_folder
        self._submit = submit
        self._discard_staged = discard_staged
        self._today = today
        self._home = home or Path.home()
        self._room: Room | None = None
        self._task_list: list[Task] = []
        self._busy = False
        self._exported: Path | None = None
        self._done.connect(self._finish_job)
        settings.exportFolderChanged.connect(self.changed)

    # ---- Properties ------------------------------------------------------------------

    def _shown(self) -> bool:
        return self._room is not None

    def _room_name(self) -> str:
        return self._room.name if self._room else ""

    def _summary(self) -> str:
        return summary(self._task_list) if self._room else ""

    def _time(self) -> str:
        return duration(self._room.time_spent_s) if self._room else ""

    def _get_busy(self) -> bool:
        return self._busy

    def _exported_text(self) -> str:
        if self._exported is None:
            return ""
        folder = shown_path(self._exported.parent, self._home)
        return f"Saved as {self._exported.name} in {folder}"

    def _folder_url(self) -> str:
        folder = self._settings.settings.export_folder
        return QUrl.fromLocalFile(folder).toString() if folder else ""

    def _status_line(self) -> str:
        return _STATUS_LINES.get(self._room.status, "") if self._room else ""

    shown = Property(bool, _shown, notify=changed)
    statusLine = Property(str, _status_line, notify=changed)  # noqa: N815
    """Where processing stands, from the room's status (the Processing bridge says more)."""
    roomName = Property(str, _room_name, notify=changed)  # noqa: N815
    summary = Property(str, _summary, notify=changed)
    timeSpent = Property(str, _time, notify=changed)  # noqa: N815
    busy = Property(bool, _get_busy, notify=changed)
    exportedText = Property(str, _exported_text, notify=changed)  # noqa: N815
    folderUrl = Property(str, _folder_url, notify=changed)  # noqa: N815
    """The last export folder as a URL for the folder picker ("" before the first export)."""

    # ---- Actions ---------------------------------------------------------------------

    def open(self, room_id: int) -> None:
        """Queue the room for processing and show the Finish screen."""

        def work() -> Then:
            self._rooms.update_progress(room_id, status="queued")
            # Finished: its undo steps (old and deleted text) aren't needed any more (F-19).
            self._undo.clear_room(room_id)
            room = self._rooms.get(room_id)
            tasks = self._tasks.for_room(room_id)
            return lambda: self._queued(room, tasks)

        self._background(work)

    def _queued(self, room: Room | None, tasks: list[Task]) -> None:
        self._show(room, tasks)
        if room is not None:
            self.processRequested.emit(room.id)

    def revisit(self, room_id: int) -> None:
        """Show a room that's already done (from Home), changing nothing (audit F-11)."""

        def work() -> Then:
            room = self._rooms.get(room_id)
            tasks = self._tasks.for_room(room_id)
            return lambda: self._show(room if room and room.status != "capturing" else None, tasks)

        self._background(work)

    def _show(self, room: Room | None, tasks: list[Task]) -> None:
        self._room, self._task_list, self._exported = room, tasks, None
        self.changed.emit()

    @Slot(str)
    def export(self, folder_url: str) -> None:
        """Write the room as Markdown into the folder picked (a file URL)."""
        room, tasks = self._room, list(self._task_list)
        folder = Path(QUrl(folder_url).toLocalFile())
        if room is None or self._busy or not folder_url:
            return
        self._settings.setProperty("exportFolder", str(folder))

        def work() -> Then:
            path = export_room(self._export_model(room, tasks), folder)
            _log.info("room %s exported", room.id)
            return lambda: self._exported_to(path)

        self._background(work)

    def _export_model(self, room: Room, tasks: list[Task]) -> ExportRoom:
        # Worker thread: read the blocks fresh, so the export has every last keystroke.
        return ExportRoom(
            name=room.name,
            platform=room.platform,
            path=room.path,
            module=room.module,
            finished_on=self._today(),
            time_spent_s=room.time_spent_s,
            tasks=tuple(
                ExportTask(
                    index=task.task_index,
                    title=task.title,
                    status=task.status,
                    blocks=tuple(
                        ExportBlock(
                            type=block.type,
                            text=block.content.text,
                            answer=block.content.answer,
                            kept=block.content.kept,
                        )
                        for block in self._blocks.for_task(task.id)
                    ),
                )
                for task in tasks
            ),
        )

    def _exported_to(self, path: Path) -> None:
        self._exported = path
        self.changed.emit()

    @Slot()
    def openFolder(self) -> None:  # noqa: N802 - Qt naming, used from QML
        """Show the export's folder in the file manager."""
        if self._exported is not None:
            self._open_folder(self._exported.parent)

    @Slot()
    def backToRoom(self) -> None:  # noqa: N802 - Qt naming, used from QML
        """Not finished after all: the room goes back to capturing, at the last task."""
        room = self._room
        if room is None or self._busy:
            return

        def work() -> Then:
            self._discard_staged(room.id)
            self._rooms.update_progress(room.id, status="capturing")
            return lambda: self._reopen(room.id)

        self._background(work)

    def _reopen(self, room_id: int) -> None:
        self._show(None, [])
        self.reopenRequested.emit(room_id)

    @Slot()
    def close(self) -> None:
        """Done: put the Finish screen away."""
        self._show(None, [])
        self.closed.emit()

    # ---- Background jobs ---------------------------------------------------------------

    def _background(self, work: Callable[[], Then]) -> None:
        self._busy = True
        self.changed.emit()

        def job() -> None:
            try:
                then = work()
            except ReconError as exc:
                _log.warning("finish step failed: %s", Safe(type(exc).__name__))
                message = exc.user_message
                then = lambda: self.failed.emit(message)  # noqa: E731 - one-line callback
            except Exception as exc:  # thread boundary: report, never leave Finish stuck
                _log.error("finish step failed: %s", Safe(type(exc).__name__))
                then = lambda: self.failed.emit(ReconError.user_message)  # noqa: E731
            self._done.emit(then)

        self._submit(job)

    def _finish_job(self, then: Then) -> None:
        self._busy = False
        self.changed.emit()
        then()
