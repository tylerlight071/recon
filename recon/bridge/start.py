"""Start a room, exposed to QML as `StartRoom` (task 1.8).

Two fields: the room name and the number of tasks. Path and module are
remembered from the last room and sit behind "More" (SPEC.md, "A room from
start to finish"). The room is created off the UI thread; `started` then
carries its ID back so the panel can open on the first task.
"""

import logging
from typing import Final

from PySide6.QtCore import Property, QObject, Signal, Slot

from recon.bridge.workers import Submit, thread_pool_submit
from recon.db.models import NewRoom, Room
from recon.db.repositories import RoomRepository
from recon.errors import ReconError
from recon.logging_setup import Safe

MAX_TASKS: Final = 50
"""More tasks than any room has; stops a typo like 700 making 700 tasks."""
NAME_LIMIT: Final = 120
PLACE_LIMIT: Final = 80

NEED_NAME: Final = "Give the room a name, then press Start."
NEED_TASKS: Final = f"Number of tasks should be a whole number from 1 to {MAX_TASKS}."

_log = logging.getLogger(__name__)


def parse_task_count(text: str) -> int | None:
    """The number of tasks typed, or None if it isn't a whole number from 1 to MAX_TASKS."""
    text = text.strip()
    if not text.isascii() or not text.isdigit():
        return None
    count = int(text)
    return count if 1 <= count <= MAX_TASKS else None


class StartRoomBridge(QObject):
    """Checks the two fields, creates the room off the UI thread and reports back."""

    changed = Signal()
    started = Signal(int)
    """The new room's ID, once it's saved."""
    _created = Signal(int)
    _failed = Signal(str)

    def __init__(
        self,
        rooms: RoomRepository,
        submit: Submit = thread_pool_submit,
        parent: QObject | None = None,
    ) -> None:
        """Use `rooms` to remember the last place and save the new room.

        Args:
            rooms: Room storage.
            submit: Runs a job off the UI thread (tests pass a synchronous one).
            parent: Qt parent.
        """
        super().__init__(parent)
        self._rooms = rooms
        self._submit = submit
        self._last_path = ""
        self._last_module = ""
        self._problem = ""
        self._busy = False
        # Emitted from the worker thread; Qt queues them back to the UI thread.
        self._created.connect(self._on_created)
        self._failed.connect(self._on_failed)
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        """Re-read the last room's path and module, and clear any old message."""
        last: list[Room] = self._rooms.recent(limit=1)
        self._last_path = last[0].path if last else ""
        self._last_module = last[0].module if last else ""
        self._problem = ""
        self.changed.emit()

    def _get_last_path(self) -> str:
        return self._last_path

    def _get_last_module(self) -> str:
        return self._last_module

    def _get_problem(self) -> str:
        return self._problem

    def _get_busy(self) -> bool:
        return self._busy

    def _get_max_tasks(self) -> int:
        return MAX_TASKS

    def _get_name_limit(self) -> int:
        return NAME_LIMIT

    def _get_place_limit(self) -> int:
        return PLACE_LIMIT

    lastPath = Property(str, _get_last_path, notify=changed)  # noqa: N815
    lastModule = Property(str, _get_last_module, notify=changed)  # noqa: N815
    problem = Property(str, _get_problem, notify=changed)
    """What to fix before starting, in plain words; "" when there's nothing."""
    busy = Property(bool, _get_busy, notify=changed)
    maxTasks = Property(int, _get_max_tasks, constant=True)  # noqa: N815
    nameLimit = Property(int, _get_name_limit, constant=True)  # noqa: N815
    placeLimit = Property(int, _get_place_limit, constant=True)  # noqa: N815

    @Slot(str, str, str, str)
    def start(self, name: str, tasks: str, path: str, module: str) -> None:
        """Create the room, or say what to fix.

        Args:
            name: The room name as typed.
            tasks: The number of tasks as typed.
            path: The learning path (may be empty).
            module: The module within the path (may be empty).
        """
        if self._busy:
            return
        count = parse_task_count(tasks)
        if not name.strip():
            self._set(problem=NEED_NAME)
            return
        if count is None:
            self._set(problem=NEED_TASKS)
            return
        new = NewRoom(
            name=name.strip()[:NAME_LIMIT],
            task_count=count,
            path=path.strip()[:PLACE_LIMIT],
            module=module.strip()[:PLACE_LIMIT],
        )
        self._set(problem="", busy=True)
        self._submit(lambda: self._create(new))

    def _create(self, new: NewRoom) -> None:
        # Worker thread: a boundary, so every failure becomes a calm message.
        try:
            room = self._rooms.create(new)
        except ReconError as exc:
            _log.warning("room not created: %s", Safe(type(exc).__name__))
            self._failed.emit(exc.user_message)
            return
        except Exception as exc:  # thread boundary: never leave Start stuck on "Starting…"
            _log.error("room not created: %s", Safe(type(exc).__name__))
            self._failed.emit(ReconError.user_message)
            return
        _log.info("room %s created with %s tasks", room.id, room.task_count)
        self._created.emit(room.id)

    def _on_created(self, room_id: int) -> None:
        self._set(busy=False)
        self.started.emit(room_id)

    def _on_failed(self, message: str) -> None:
        self._set(problem=message, busy=False)

    def _set(self, *, problem: str | None = None, busy: bool | None = None) -> None:
        if problem is not None:
            self._problem = problem
        if busy is not None:
            self._busy = busy
        self.changed.emit()
