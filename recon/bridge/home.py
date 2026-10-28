"""The Home screen's data, exposed to QML as `HomeModel` (task 1.7).

One primary action: "Start a room", or "Carry on with <room>" when one is in
progress. The "Where was I?" card remembers for the user (ADHD rule 6): the
room, "Task 4 of 7", how long ago, and the last line written. Times are
calm ("2 days ago"), never overdue counts (ADHD rule 8).
"""

from collections.abc import Callable
from datetime import datetime
from typing import Final

from PySide6.QtCore import Property, QObject, Signal, Slot

from recon.db.models import Room
from recon.db.repositories import BlockRepository, RoomRepository

RECENT_LIMIT: Final = 5
LAST_NOTE_LIMIT: Final = 80
_STATUS_WORDS: Final = {
    "queued": "Processing",
    "processing": "Processing",
    "in_review": "Ready to review",
    "done": "Done",
}

type Clock = Callable[[], datetime]


_MINUTE: Final = 60
_HOUR: Final = 60 * _MINUTE
_DAY: Final = 24 * _HOUR
# (shown while the age is under this many seconds, wording)
_AGES: Final[tuple[tuple[int, Callable[[int], str]], ...]] = (
    (_MINUTE, lambda _s: "just now"),
    (_HOUR, lambda s: _plural(s // _MINUTE, "minute")),
    (_DAY, lambda s: _plural(s // _HOUR, "hour")),
    (2 * _DAY, lambda _s: "yesterday"),
    (14 * _DAY, lambda s: f"{s // _DAY} days ago"),
    (60 * _DAY, lambda s: _plural(s // (7 * _DAY), "week")),
)


def ago(then: datetime, now: datetime) -> str:
    """How long ago, in plain words: "just now", "5 minutes ago", "yesterday", "3 weeks ago"."""
    seconds = max(0, int((now - then).total_seconds()))
    for limit, words in _AGES:
        if seconds < limit:
            return words(seconds)
    return f"on {then.astimezone(now.tzinfo).strftime('%-d %B %Y')}"


def _plural(n: int, unit: str) -> str:
    return f"{n} {unit} ago" if n == 1 else f"{n} {unit}s ago"


def last_line(text: str, limit: int = LAST_NOTE_LIMIT) -> str:
    """The last non-empty line of a note, trimmed and shortened to fit the card."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    line = lines[-1]
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "\N{HORIZONTAL ELLIPSIS}"


def task_progress(room: Room) -> str:
    """Progress in the room, as "Task 4 of 7"."""
    return f"Task {room.last_task_index} of {room.task_count}"


class HomeBridge(QObject):
    """Reads rooms for Home and turns the primary button into start or resume."""

    changed = Signal()
    startRequested = Signal()  # noqa: N815 - Qt naming, used from QML
    resumeRequested = Signal(int)  # noqa: N815 - Qt naming, used from QML
    finishedRequested = Signal(int)  # noqa: N815 - Qt naming; a done room's Finish screen

    def __init__(
        self,
        rooms: RoomRepository,
        blocks: BlockRepository,
        clock: Clock,
        parent: QObject | None = None,
    ) -> None:
        """Read from `rooms` and `blocks`; `clock` gives "now" for the "ago" wording."""
        super().__init__(parent)
        self._rooms = rooms
        self._blocks = blocks
        self._clock = clock
        self._current: Room | None = None
        self._last_note = ""
        self._recent: list[dict[str, object]] = []
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        """Re-read rooms (when Home is shown, and after a room changes)."""
        now = self._clock()
        self._current = self._rooms.current()
        latest = self._blocks.latest_written(self._current.id) if self._current else None
        self._last_note = last_line(latest.content.text) if latest else ""
        current_id = self._current.id if self._current else None
        self._recent = [
            self._row(room, now)
            for room in self._rooms.recent(limit=RECENT_LIMIT + 1)
            if room.id != current_id
        ][:RECENT_LIMIT]
        self.changed.emit()

    def _row(self, room: Room, now: datetime) -> dict[str, object]:
        place = " · ".join(part for part in (room.path, room.module) if part)
        state = task_progress(room) if room.status == "capturing" else _STATUS_WORDS[room.status]
        return {
            "id": room.id,
            "name": room.name,
            "detail": f"{place} · {state}" if place else state,
            "when": ago(room.updated_at, now),
            "canResume": room.status == "capturing",
            # A done room opens its Finish screen again: export, or back to the room (F-11).
            "canOpen": room.status in {"capturing", "done"},
        }

    def _has_current(self) -> bool:
        return self._current is not None

    def _primary_text(self) -> str:
        return f"Carry on with {self._current.name}" if self._current else "Start a room"

    def _current_name(self) -> str:
        return self._current.name if self._current else ""

    def _current_task(self) -> str:
        return task_progress(self._current) if self._current else ""

    def _current_when(self) -> str:
        return ago(self._current.updated_at, self._clock()) if self._current else ""

    def _get_last_note(self) -> str:
        return self._last_note

    def _get_recent(self) -> list[dict[str, object]]:
        return self._recent

    hasCurrent = Property(bool, _has_current, notify=changed)  # noqa: N815
    primaryText = Property(str, _primary_text, notify=changed)  # noqa: N815
    currentName = Property(str, _current_name, notify=changed)  # noqa: N815
    currentTask = Property(str, _current_task, notify=changed)  # noqa: N815
    currentWhen = Property(str, _current_when, notify=changed)  # noqa: N815
    lastNote = Property(str, _get_last_note, notify=changed)  # noqa: N815
    recentRooms = Property(list, _get_recent, notify=changed)  # noqa: N815

    @Slot()
    def primary(self) -> None:
        """The one big button: carry on with the current room, or start one."""
        if self._current is not None:
            self.resumeRequested.emit(self._current.id)
        else:
            self.startRequested.emit()

    @Slot()
    def startNew(self) -> None:  # noqa: N802 - Qt naming, used from QML
        """Start a different room while one is in progress."""
        self.startRequested.emit()

    @Slot(int)
    def resume(self, room_id: int) -> None:
        """Open a recent room: carry on capturing it, or, if it's done, its Finish screen."""
        room = self._rooms.get(room_id)
        if room is None:
            return
        if room.status == "capturing":
            self.resumeRequested.emit(room_id)
        elif room.status == "done":
            self.finishedRequested.emit(room_id)
