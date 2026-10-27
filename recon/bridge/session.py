"""The room session in the panel, exposed to QML as `RoomSession` (task 1.9).

One task at a time: header (room, "Task 3 of 7", ring, and the `Focus` timer), an optional
task title, the task's blocks (never a blank page: a Key idea block is always
there), the add bar, "Previous task" and "Skip this task", and one primary
button, "Next task" or "Finish room".

Edits pass through the flag filter and into the autosave queue on every
keystroke (hard rules 2 and 7). Ctrl+Z / Ctrl+Shift+Z undo and redo within
the task on screen (adds, deletes, moves and typing, about a word at a time);
`bridge/undo.py` keeps the steps and `undo_log` keeps them across restarts.
Everything else that writes (opening a task, adding a block, saving the title,
moving between tasks) runs in order on a private worker thread, and the
result comes back to the UI thread as a signal.
"""

import logging
import time
from collections.abc import Callable
from typing import Final, Protocol

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from recon.bridge.blocks_model import BlockListModel, add_bar_entries, kind_named
from recon.bridge.flags import FlagGuard
from recon.bridge.undo import Field, Step, UndoHistory
from recon.bridge.workers import Submit
from recon.db.models import (
    Block,
    BlockContent,
    InsertBlock,
    MoveBlock,
    RemoveBlock,
    Room,
    SetContent,
    Task,
    TaskStatus,
    UndoAction,
    UndoEntry,
)
from recon.db.repositories import (
    BlockRepository,
    RoomRepository,
    TaskRepository,
    UndoRepository,
)
from recon.errors import ReconError
from recon.logging_setup import Safe

TITLE_SAVE_MS: Final = 500
"""The task title saves this long after the last keystroke (hard rule 7)."""

type Then = Callable[[], None]
"""What to do on the UI thread once a background job has finished."""

_log = logging.getLogger(__name__)


class Autosave(Protocol):
    """What the session needs from `recon.db.autosave.AutosaveQueue`."""

    def put(self, block_id: int, content: BlockContent) -> None:
        """Queue a block's latest content."""

    def flush(self, timeout_s: float = 5.0) -> bool:
        """Write everything queued now."""


class RoomSessionBridge(QObject):
    """Loads a room into the panel and moves through its tasks."""

    changed = Signal()
    busyChanged = Signal()  # noqa: N815 - Qt naming, used from QML
    taskShown = Signal()  # noqa: N815 - Qt naming, used from QML
    """A task (or room) was opened: refill the title field."""
    focusBlock = Signal(int)  # noqa: N815 - Qt naming, used from QML
    """Put the cursor in this block (a task opened, or a block was added)."""
    replaceText = Signal(int, str, str)  # noqa: N815 - Qt naming, used from QML
    """(block, "text" or "answer", text): show this in that editor ("Not a flag, keep it")."""
    taskCompleted = Signal()  # noqa: N815 - Qt naming, used from QML
    """Tyler finished a task with Next: play the tick."""
    finishRequested = Signal(int)  # noqa: N815 - Qt naming; the room ID (Finish, task 1.13)
    failed = Signal(str)
    """Something couldn't be saved: a calm message for a toast."""
    activity = Signal()
    """Tyler did something in the session (the timer counts while he's here)."""
    blockDeleted = Signal(int)  # noqa: N815 - Qt naming, used from QML
    """A block was deleted: show the 10 s Undo toast (ADHD rule 4)."""
    _done = Signal(object)

    def __init__(  # noqa: PLR0913 - every collaborator is injected (CLAUDE.md)
        self,
        repos: tuple[RoomRepository, TaskRepository, BlockRepository, UndoRepository],
        autosave: Autosave,
        flag_guard: FlagGuard,
        *,
        submit: Submit,
        monotonic: Callable[[], float] = time.monotonic,
        parent: QObject | None = None,
    ) -> None:
        """Wire the session to storage.

        Args:
            repos: Rooms, tasks, blocks and the undo log.
            autosave: Saves block edits within half a second.
            flag_guard: Strips flags from edits and offers "Not a flag, keep it".
            submit: Runs a job off the UI thread, in order (tests pass a synchronous one).
            monotonic: Seconds, for grouping typing into undo steps.
            parent: Qt parent.
        """
        super().__init__(parent)
        self._rooms, self._tasks_repo, self._blocks, self._undo_repo = repos
        self._autosave = autosave
        self._guard = flag_guard
        self._submit = submit
        self._room: Room | None = None
        self._tasks: list[Task] = []
        self._index = 0
        self._busy = False
        self._pending_title: str | None = None
        # Block ID -> (field, text as typed, text after a hex lookalike was skipped).
        self._skipped: dict[int, tuple[Field, str, str]] = {}
        self._model = BlockListModel(self)
        self._history = UndoHistory(monotonic)
        # True while Undo puts text back, so the editors' echo isn't recorded as typing.
        self._replaying = False
        self._title_timer = QTimer(self, singleShot=True, interval=TITLE_SAVE_MS)
        self._title_timer.timeout.connect(self._save_title)
        # A bound method, so Qt queues worker results back to the UI thread.
        self._done.connect(self._finish_job)
        flag_guard.keptRestored.connect(self._restore_kept)

    # ---- Properties ------------------------------------------------------------

    def _task(self) -> Task | None:
        return self._tasks[self._index - 1] if self._room and self._tasks else None

    def _has_room(self) -> bool:
        return self._room is not None

    def _room_name(self) -> str:
        return self._room.name if self._room else ""

    def _task_index(self) -> int:
        return self._index

    def _task_count(self) -> int:
        return len(self._tasks)

    def _task_label(self) -> str:
        return f"Task {self._index} of {len(self._tasks)}" if self._room else ""

    def _task_title(self) -> str:
        task = self._task()
        return task.title if task else ""

    def _title_hint(self) -> str:
        return f"Task {self._index}" if self._room else ""

    def _progress(self) -> float:
        finished = sum(task.status != "open" for task in self._tasks)
        return finished / len(self._tasks) if self._tasks else 0.0

    def _is_last(self) -> bool:
        return bool(self._tasks) and self._index == len(self._tasks)

    def _can_go_back(self) -> bool:
        return self._index > 1

    def _primary_text(self) -> str:
        return "Finish room" if self._is_last() else "Next task"

    def _get_busy(self) -> bool:
        return self._busy

    def _get_blocks(self) -> BlockListModel:
        return self._model

    def _get_add_bar(self) -> list[dict[str, object]]:
        return add_bar_entries()

    hasRoom = Property(bool, _has_room, notify=changed)  # noqa: N815
    roomName = Property(str, _room_name, notify=changed)  # noqa: N815
    taskIndex = Property(int, _task_index, notify=changed)  # noqa: N815
    taskCount = Property(int, _task_count, notify=changed)  # noqa: N815
    taskLabel = Property(str, _task_label, notify=changed)  # noqa: N815
    taskTitle = Property(str, _task_title, notify=changed)  # noqa: N815
    titleHint = Property(str, _title_hint, notify=changed)  # noqa: N815
    progress = Property(float, _progress, notify=changed)
    isLastTask = Property(bool, _is_last, notify=changed)  # noqa: N815
    primaryText = Property(str, _primary_text, notify=changed)  # noqa: N815
    canGoBack = Property(bool, _can_go_back, notify=changed)  # noqa: N815
    busy = Property(bool, _get_busy, notify=busyChanged)
    blocks = Property(QObject, _get_blocks, constant=True)
    addBar = Property(list, _get_add_bar, constant=True)  # noqa: N815

    # ---- Opening a room ------------------------------------------------------------

    @Slot(int)
    def open(self, room_id: int) -> None:
        """Load a room still being captured, at the task Tyler was on."""
        # A title still waiting to save belongs to the task on screen now.
        self._save_title()

        def work() -> Then:
            room = self._rooms.get(room_id)
            if room is None or room.status != "capturing":
                _log.warning("room %s can't be opened for capture", room_id)
                return lambda: None
            tasks = self._tasks_repo.for_room(room_id)
            index = max(1, min(room.last_task_index, len(tasks)))
            blocks = self._starter_blocks(tasks[index - 1])
            history = self._undo_repo.for_room(room_id)
            return lambda: self._show(room, tasks, index, blocks, history)

        self._background(work)

    def _starter_blocks(self, task: Task) -> list[Block]:
        # Worker thread. Never a blank page: a Key idea block is always there.
        self._blocks.ensure_starter_block(task.id)
        return self._blocks.for_task(task.id)

    def _show(
        self,
        room: Room,
        tasks: list[Task],
        index: int,
        blocks: list[Block],
        history: list[UndoEntry] | None = None,
    ) -> None:
        if history is not None:
            self._history.load(history)
        self._history.close_group()
        self._room, self._tasks, self._index = room, tasks, index
        self.activity.emit()
        self._skipped.clear()
        self._model.reset(blocks)
        self.changed.emit()
        self.taskShown.emit()
        first = self._model.first_id()
        if first is not None:
            self.focusBlock.emit(first)

    # ---- Editing ------------------------------------------------------------------------

    @Slot(int, str, result=str)
    def edit(self, block_id: int, text: str) -> str:
        """Tyler typed in a block: strip flags, queue the save, return what to show.

        Args:
            block_id: The block.
            text: Everything in its editor now.

        Returns:
            The text the editor should show (flags removed).
        """
        return self._edit(block_id, "text", text)

    @Slot(int, str, result=str)
    def editAnswer(self, block_id: int, text: str) -> str:  # noqa: N802 - Qt naming, used from QML
        """Tyler typed a Room question's answer: same rules as `edit` (answers attract flags)."""
        return self._edit(block_id, "answer", text)

    def _edit(self, block_id: int, field: Field, text: str) -> str:
        content = self._model.content(block_id)
        if content is None:
            return text
        self.activity.emit()
        shown = self._guard.clean(block_id, text, list(content.kept))
        if shown != text:
            self._skipped[block_id] = (field, text, shown)
        old = (content.answer or "") if field == "answer" else content.text
        task_id = self._task_id()
        if shown != old and task_id is not None and not self._replaying:
            step = self._history.typed(
                task_id, block_id=block_id, field_name=field, before=content, new=shown
            )
            if step is not None:
                self._save_step(step)
        updated = content.model_copy(update={field: shown})
        self._model.set_content(block_id, updated, notify=False)
        self._autosave.put(block_id, updated)
        return shown

    def _restore_kept(self, block_id: int, kept: str) -> None:
        # "Not a flag, keep it": put the string back where it was, if nothing changed
        # since; otherwise at the end, so newer typing is never lost.
        content = self._model.content(block_id)
        field, typed, shown = self._skipped.pop(block_id, ("text", "", ""))
        if content is None or kept not in typed:
            return
        now = (content.answer or "") if field == "answer" else content.text
        text = typed if now == shown else f"{now.rstrip()} {kept}".lstrip()
        keep = content.kept if kept in content.kept else (*content.kept, kept)
        updated = content.model_copy(update={field: text, "kept": keep})
        self._record(SetContent(block_id=block_id, content=content))
        self._set_content(block_id, updated, (field,))

    @Slot(str)
    def setTitle(self, title: str) -> None:  # noqa: N802 - Qt naming, used from QML
        """Tyler typed the task title; it saves within half a second, even while he types."""
        if self._task() is None:
            return
        self.activity.emit()
        self._pending_title = title
        # Max-latency, like block autosave (hard rule 7): steady typing can't put
        # the save off, so a title is stored within half a second of its first change.
        if not self._title_timer.isActive():
            self._title_timer.start()

    def _save_title(self) -> None:
        task, title = self._task(), self._take_title()
        if task is None or title is None:
            return

        def work() -> Then:
            self._tasks_repo.set_title(task.id, title)
            return lambda: None

        self._background(work, busy=False)

    def _take_title(self) -> str | None:
        # The unsaved title (trimmed), now also shown as this task's title.
        self._title_timer.stop()
        title, self._pending_title = self._pending_title, None
        task = self._task()
        if title is None or task is None:
            return None
        title = title.strip()
        self._tasks[self._index - 1] = task.model_copy(update={"title": title})
        return title

    def close(self) -> None:
        """Save an unsaved title now (at quit; the event loop has stopped)."""
        task, title = self._task(), self._take_title()
        if task is not None and title is not None:
            try:
                self._tasks_repo.set_title(task.id, title)
            except ReconError as exc:
                _log.warning("title not saved at quit: %s", Safe(type(exc).__name__))

    @Slot(str)
    def addBlock(self, block_type: str) -> None:  # noqa: N802 - Qt naming, used from QML
        """Add a block of this type at the end of the task and put the cursor in it."""
        task, kind = self._task(), kind_named(block_type)
        if task is None or kind is None or not kind.available or self._busy:
            return

        def work() -> Then:
            block = self._blocks.add(task.id, kind.type)
            return lambda: self._added(block)

        self._background(work)

    def _added(self, block: Block) -> None:
        if self._task() is not None and self._task_id() == block.task_id:
            self._model.append(block)
            self._record(RemoveBlock(block_id=block.id))
            self.focusBlock.emit(block.id)

    @Slot(int, int)
    def moveBlock(self, block_id: int, position: int) -> None:  # noqa: N802 - Qt naming, used from QML
        """Move a block within the task (drag, or Alt+Up / Alt+Down); the rest close up."""
        undo = self._move_block(block_id, position)
        if undo is not None:
            self._record(undo)

    def _move_block(self, block_id: int, position: int) -> MoveBlock | None:
        # Move now on screen, then in storage; returns the move that goes back.
        old = self._model.row(block_id)
        target = self._model.move(block_id, position)
        if old is None or target is None:
            return None

        def work() -> Then:
            self._blocks.move(block_id, target)
            return lambda: None

        self._background(work, busy=False)
        self.focusBlock.emit(block_id)
        return MoveBlock(block_id=block_id, position=old)

    @Slot(int)
    def deleteBlock(self, block_id: int) -> None:  # noqa: N802 - Qt naming, used from QML
        """Delete a block (never the last one: never a blank page); Undo brings it back."""
        if self._busy or self._model.rowCount() <= 1:
            return
        undo = self._remove_block(block_id)
        if undo is not None:
            self._record(undo)
            self.blockDeleted.emit(block_id)

    def _remove_block(self, block_id: int) -> InsertBlock | None:
        # Remove now on screen, then in storage; returns the insert that goes back.
        block, row = self._model.block(block_id), self._model.row(block_id)
        if block is None or row is None or not self._model.remove(block_id):
            return None

        def work() -> Then:
            self._blocks.delete(block_id)
            return lambda: None

        self._background(work, busy=False)
        neighbour = self._model.id_at(max(0, row - 1))
        if neighbour is not None:
            self.focusBlock.emit(neighbour)
        return InsertBlock(block=block)

    # ---- Undo and redo ---------------------------------------------------------------

    @Slot()
    def undo(self) -> None:
        """Ctrl+Z: step back once in the task on screen."""
        task_id = self._task_id()
        if task_id is None or self._busy:
            return
        step = self._history.pop_undo(task_id)
        if step is not None:
            self._apply(step.action, lambda back: self._history.push_redo(task_id, back), step)

    @Slot()
    def redo(self) -> None:
        """Ctrl+Shift+Z: step forward again after an undo."""
        task_id = self._task_id()
        if task_id is None or self._busy:
            return
        action = self._history.pop_redo(task_id)
        if action is not None:
            self._apply(
                action, lambda back: self._save_step(self._history.push_undo(task_id, back))
            )

    @Slot(int)
    def undoDelete(self, block_id: int) -> None:  # noqa: N802 - Qt naming, used from QML
        """The delete toast's Undo: bring that block back, whatever happened since.

        Works with no room open too (the toast outlives "Finish room"): the block
        goes back into its task in storage, and shows when the task is opened.
        """
        if self._busy:
            return
        step = self._history.take_insert(block_id)
        if step is not None:
            self._apply(step.action, lambda back: self._history.push_redo(step.task_id, back), step)

    def _record(self, action: UndoAction) -> None:
        self.activity.emit()
        task_id = self._task_id()
        if task_id is not None:
            self._save_step(self._history.record(task_id, action))

    def _apply(
        self, action: UndoAction, then: Callable[[UndoAction], None], taken: Step | None = None
    ) -> None:
        # Do `action` and hand its opposite to `then` (for the other stack). `taken`, the
        # undo step being used, leaves undo_log only after its change is saved.
        if isinstance(action, InsertBlock):
            self._insert_block(action.block, then, taken)
            return
        if isinstance(action, SetContent):
            current = self._model.content(action.block_id)
            if current is not None:
                self._set_content(action.block_id, action.content)
                self.focusBlock.emit(action.block_id)
                then(SetContent(block_id=action.block_id, content=current))
        elif isinstance(action, RemoveBlock):
            insert = self._remove_block(action.block_id)
            if insert is not None:
                then(insert)
        else:
            move = self._move_block(action.block_id, action.position)
            if move is not None:
                then(move)
        if taken is not None:
            self._forget(taken)  # queued behind the change's own write (one serial worker)

    def _insert_block(
        self, block: Block, then: Callable[[UndoAction], None], taken: Step | None
    ) -> None:
        # One job: the block comes back, and only then is its undo step forgotten, so a
        # failed restore leaves the step in undo_log to try again.
        def work() -> Then:
            restored = self._blocks.restore(block)
            if taken is not None and taken.entry_id is not None:
                self._undo_repo.delete(taken.entry_id)
            return lambda: self._inserted(restored, then)

        self._background(work)

    def _inserted(self, block: Block, then: Callable[[UndoAction], None]) -> None:
        if self._task_id() == block.task_id:
            self._model.insert(block)
            self.focusBlock.emit(block.id)
        then(RemoveBlock(block_id=block.id))

    def _set_content(
        self, block_id: int, content: BlockContent, fields: tuple[Field, ...] = ("text", "answer")
    ) -> None:
        # Show `content` in the block's editors (without recording it as typing) and save it.
        self._model.set_content(block_id, content, notify=True)
        self._autosave.put(block_id, content)
        self._replaying = True
        try:
            for field in fields:
                value = (content.answer or "") if field == "answer" else content.text
                self.replaceText.emit(block_id, field, value)
        finally:
            self._replaying = False

    def _save_step(self, step: Step) -> None:
        room = self._room
        if room is None:
            return

        def work() -> Then:
            step.entry_id = self._undo_repo.push(room.id, step.task_id, step.action).id
            return lambda: None

        self._background(work, busy=False)

    def _forget(self, step: Step) -> None:
        # Runs after the step's own save (the worker is serial), so its ID is known by then.
        def work() -> Then:
            if step.entry_id is not None:
                self._undo_repo.delete(step.entry_id)
            return lambda: None

        self._background(work, busy=False)

    @Slot()
    def closeRoom(self) -> None:  # noqa: N802 - Qt naming, used from QML
        """Put the room away (Finish): save what's pending; the panel then shows no room."""
        self._save_title()

        def work() -> Then:
            self._autosave.flush()
            return lambda: None

        # On the serial worker, so it lands before anything reads the room back.
        self._background(work, busy=False)
        self._room, self._tasks, self._index = None, [], 0
        self._skipped.clear()
        self._history.close_group()
        self._model.reset([])
        self.changed.emit()

    def current_task(self) -> Task | None:
        """The task on screen (with its recorded time), or None."""
        return self._task()

    def _task_id(self) -> int | None:
        task = self._task()
        return task.id if task else None

    # ---- Moving on ---------------------------------------------------------------------

    @Slot()
    def next(self) -> None:
        """Finish this task and open the next (or finish the room on the last one)."""
        self._move(1, "done")

    @Slot()
    def skip(self) -> None:
        """Skip this task: no shame, it's just marked skipped and the next one opens."""
        self._move(1, "skipped")

    @Slot()
    def previous(self) -> None:
        """Go back one task to add or fix something; no task's status changes."""
        self._move(-1, None)

    def _move(self, step: int, status: TaskStatus | None) -> None:
        # Save everything, mark the task (unless going back), then open the target task.
        room, task = self._room, self._task()
        target = self._index + step
        if room is None or task is None or self._busy or target < 1:
            return
        title, tasks = self._take_title(), list(self._tasks)

        def work() -> Then:
            self._autosave.flush()
            if title is not None:
                self._tasks_repo.set_title(task.id, title)
            if status is not None:
                self._tasks_repo.set_status(task.id, status)
            if target > len(tasks):
                done = self._tasks_repo.for_room(room.id)
                return lambda: self._room_finished(room, done, status)
            self._rooms.update_progress(room.id, last_task_index=target)
            blocks = self._starter_blocks(tasks[target - 1])
            fresh = self._tasks_repo.for_room(room.id)
            return lambda: self._moved_on(room, fresh, target, blocks, status)

        self._background(work)

    def _moved_on(
        self,
        room: Room,
        tasks: list[Task],
        index: int,
        blocks: list[Block],
        status: TaskStatus | None,
    ) -> None:
        if status == "done":
            self.taskCompleted.emit()
        self._show(room, tasks, index, blocks)

    def _room_finished(self, room: Room, tasks: list[Task], status: TaskStatus | None) -> None:
        self._tasks = tasks
        self.changed.emit()
        if status == "done":
            self.taskCompleted.emit()
        self.finishRequested.emit(room.id)

    # ---- Background jobs -------------------------------------------------------------

    def _background(self, work: Callable[[], Then], *, busy: bool = True) -> None:
        if busy:
            self._set_busy(value=True)

        def job() -> None:
            try:
                then = work()
            except ReconError as exc:
                _log.warning("session write failed: %s", Safe(type(exc).__name__))
                then = self._failure(exc.user_message)
            except Exception as exc:  # thread boundary: report, never leave the panel stuck
                _log.error("session write failed: %s", Safe(type(exc).__name__))
                then = self._failure(ReconError.user_message)
            self._done.emit((then, busy))

        self._submit(job)

    def _failure(self, message: str) -> Then:
        return lambda: self.failed.emit(message)

    def _finish_job(self, result: tuple[Then, bool]) -> None:
        then, was_busy = result
        if was_busy:
            self._set_busy(value=False)
        then()

    def _set_busy(self, *, value: bool) -> None:
        if self._busy != value:
            self._busy = value
            self.busyChanged.emit()
