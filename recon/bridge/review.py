"""The review screen, exposed to QML as `ReviewModel` (task 2.6; `Review` is the screen's own name).

Opens a room's staged run in the main window, split into the spec's sections:
the room note as Obsidian will show it, new notes, additions to existing
notes (only what changes), and notes left alone. Links and flags arrive in
Phase 3. A sticky footer holds Apply (the one primary button) and Discard,
which asks once.

- **Apply** writes the vault (`Processing.apply_run`). If a note changed in
  Obsidian since this review was prepared, nothing is written; the screen
  says so and offers "Re-check", which prepares the room again.
- **Discard** throws the staged notes away and reopens the room in the panel,
  exactly as it was.
"""

import logging
from collections.abc import Callable

from PySide6.QtCore import Property, QObject, Signal, Slot

from recon.bridge.workers import Submit
from recon.engine.review import Review, ReviewNote
from recon.engine.stage import Applied
from recon.errors import ApplyConflict, ReconError
from recon.logging_setup import Safe

type Then = Callable[[], None]
type Load = Callable[[int], tuple[Review, str] | None]
"""A room's review and its name, or None if nothing is staged for it."""

_log = logging.getLogger(__name__)


def _rows(notes: tuple[ReviewNote, ...]) -> list[dict[str, str]]:
    return [
        {
            "title": n.title,
            "kind": "Concept" if n.kind == "concept" else "Tool",
            "markdown": n.markdown,
        }
        for n in notes
    ]


class ReviewBridge(QObject):
    """One staged run on screen, with Apply, Discard and Re-check."""

    changed = Signal()
    opened = Signal()
    nothingToReview = Signal(int)  # noqa: N815 - Qt naming; the room ID
    applied = Signal(int, int)  # room ID, notes written
    discarded = Signal(int)
    recheckRequested = Signal(int)  # noqa: N815 - Qt naming; the room ID
    _done = Signal(object)

    def __init__(  # noqa: PLR0913 - every collaborator is injected (CLAUDE.md)
        self,
        load: Load,
        apply: Callable[[str], Applied],
        discard: Callable[[str], None],
        requeue: Callable[[str], int],
        *,
        submit: Submit,
        parent: QObject | None = None,
    ) -> None:
        """Wire the review to processing.

        Args:
            load: The room's newest staged run, for the screen.
            apply: Applies a run (raises ApplyConflict if a note changed).
            discard: Discards a run; its room goes back to capturing.
            requeue: Discards a run and queues its room again; returns the room.
            submit: Runs each step off the UI thread, in order.
            parent: Qt parent.
        """
        super().__init__(parent)
        self._load, self._apply, self._discard, self._requeue = load, apply, discard, requeue
        self._submit = submit
        self._review: Review | None = None
        self._room_name = ""
        self._busy = False
        self._conflict = False
        self._problem = ""
        self._done.connect(lambda then: then())

    # ---- Properties --------------------------------------------------------------------

    def _shown(self) -> bool:
        return self._review is not None

    def _get_room_name(self) -> str:
        return self._room_name

    def _room_note(self) -> str:
        review = self._review
        return review.room.markdown if review and review.room else ""

    def _new(self) -> list[dict[str, str]]:
        return _rows(self._review.new) if self._review else []

    def _additions(self) -> list[dict[str, str]]:
        return _rows(self._review.additions) if self._review else []

    def _skipped(self) -> list[str]:
        return [n.title for n in self._review.skipped] if self._review else []

    def _writes(self) -> int:
        return self._review.writes if self._review else 0

    def _get_busy(self) -> bool:
        return self._busy

    def _get_conflict(self) -> bool:
        return self._conflict

    def _get_problem(self) -> str:
        return self._problem

    shown = Property(bool, _shown, notify=changed)
    roomName = Property(str, _get_room_name, notify=changed)  # noqa: N815
    roomNote = Property(str, _room_note, notify=changed)  # noqa: N815
    """The room note as Markdown Qt can render (`engine.review.for_display`)."""
    newNotes = Property(list, _new, notify=changed)  # noqa: N815
    additions = Property(list, _additions, notify=changed)
    skipped = Property(list, _skipped, notify=changed)
    writes = Property(int, _writes, notify=changed)
    busy = Property(bool, _get_busy, notify=changed)
    conflict = Property(bool, _get_conflict, notify=changed)
    """A note changed since this review was prepared: offer Re-check."""
    problem = Property(str, _get_problem, notify=changed)

    # ---- Actions -----------------------------------------------------------------------

    @Slot(int)
    def open(self, room_id: int) -> None:
        """Load the room's staged run and show it (or say there's nothing to review)."""

        def work() -> Then:
            loaded = self._load(room_id)
            if loaded is None:
                return lambda: self.nothingToReview.emit(room_id)
            review, name = loaded
            return lambda: self._show(review, name)

        self._background(work)

    def _show(self, review: Review, name: str) -> None:
        self._review, self._room_name = review, name
        self._conflict, self._problem = False, ""
        self.changed.emit()
        self.opened.emit()

    @Slot()
    def apply(self) -> None:
        """Write the notes into the vault."""
        review = self._review
        if review is None or self._busy:
            return

        def work() -> Then:
            applied = self._apply(review.run_id)
            return lambda: self._finish(lambda: self.applied.emit(review.room_id, applied.written))

        self._background(work)

    @Slot()
    def discard(self) -> None:
        """Throw the notes away (Discard asked once already) and reopen the room."""
        review = self._review
        if review is None or self._busy:
            return

        def work() -> Then:
            self._discard(review.run_id)
            return lambda: self._finish(lambda: self.discarded.emit(review.room_id))

        self._background(work)

    @Slot()
    def recheck(self) -> None:
        """After a conflict: prepare the room again from the vault as it is now."""
        review = self._review
        if review is None or self._busy:
            return

        def work() -> Then:
            room_id = self._requeue(review.run_id)
            return lambda: self._finish(lambda: self.recheckRequested.emit(room_id))

        self._background(work)

    def _finish(self, then: Then) -> None:
        self._review, self._room_name = None, ""
        self.changed.emit()
        then()

    # ---- Background jobs ----------------------------------------------------------------

    def _background(self, work: Callable[[], Then]) -> None:
        self._busy, self._problem, self._conflict = True, "", False
        self.changed.emit()

        def job() -> None:
            # Thread boundary: report a problem on the screen, never leave it stuck.
            try:
                then = work()
            except ApplyConflict as exc:
                then = self._failed(exc.user_message, conflict=True)
            except ReconError as exc:
                _log.warning("review step failed: %s", Safe(type(exc).__name__))
                then = self._failed(exc.user_message)
            except Exception as exc:  # thread boundary
                _log.error("review step failed: %s", Safe(type(exc).__name__))
                then = self._failed(ReconError.user_message)
            self._done.emit(lambda: self._idle(then))

        self._submit(job)

    def _failed(self, message: str, *, conflict: bool = False) -> Then:
        def show() -> None:
            self._problem, self._conflict = message, conflict

        return show

    def _idle(self, then: Then) -> None:
        self._busy = False
        then()
        self.changed.emit()
