"""Undo bookkeeping for the room session (task 1.11): stacks, grouping, lookups.

Each task has an undo stack and a redo stack of actions that put things back
(see `recon.db.models.UndoAction`). Undo steps are also kept in `undo_log`, so
a deleted block can still come back after a restart; `Step.entry_id` is the
row once it's been written. Redo lives in memory only.

Typing is grouped so one Ctrl+Z undoes about a word, not a keystroke: a new
group starts on another block or field, after a pause, or once a word ends.
No Qt and no storage here: the session applies actions and saves steps.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final, Literal

from recon.db.models import (
    BlockContent,
    InsertBlock,
    SetContent,
    UndoAction,
    UndoEntry,
    remap_action,
)

GROUP_PAUSE_S: Final = 1.0
"""Typing after a pause this long starts a new undo step."""

type Field = Literal["text", "answer"]


@dataclass
class Step:
    """One undo step: the action that goes back, and its `undo_log` row once saved."""

    task_id: int
    action: UndoAction
    entry_id: int | None = None


@dataclass
class _Group:
    task_id: int
    block_id: int
    field: Field
    last: float
    closed: bool = False


@dataclass
class UndoHistory:
    """Per-task undo and redo stacks, with typing grouped into word-sized steps."""

    monotonic: Callable[[], float]
    undo: dict[int, list[Step]] = field(default_factory=dict)
    redo: dict[int, list[UndoAction]] = field(default_factory=dict)
    _group: _Group | None = None

    def load(self, entries: list[UndoEntry]) -> None:
        """Replace everything with steps read back from `undo_log` (oldest first)."""
        self.undo = {}
        self.redo = {}
        self._group = None
        for entry in entries:
            self.undo.setdefault(entry.task_id, []).append(
                Step(entry.task_id, entry.action, entry.id)
            )

    def record(self, task_id: int, action: UndoAction) -> Step:
        """Tyler did something new: remember how to go back; redo no longer applies."""
        self.close_group()
        return self._push(task_id, action)

    def typed(
        self, task_id: int, *, block_id: int, field_name: Field, before: BlockContent, new: str
    ) -> Step | None:
        """Tyler typed: start a new step if this is a new group, else extend the open one.

        Args:
            task_id: The task on screen.
            block_id: The block typed in.
            field_name: "text" or "answer".
            before: The block's content before this keystroke.
            new: The field's text after it.

        Returns:
            The new step to save, or None when this keystroke joins the open group.
        """
        old = (before.answer or "") if field_name == "answer" else before.text
        now = self.monotonic()
        group = self._group
        step = None
        if (
            group is None
            or group.closed
            or (group.task_id, group.block_id, group.field) != (task_id, block_id, field_name)
            or now - group.last >= GROUP_PAUSE_S
        ):
            step = self._push(task_id, SetContent(block_id=block_id, content=before))
            group = self._group = _Group(task_id, block_id, field_name, now)
        group.last = now
        # A finished word ends the group, so the next keystroke starts a new step.
        group.closed = new[-1:].isspace() and not old[-1:].isspace()
        return step

    def close_group(self) -> None:
        """Whatever comes next starts a new step."""
        self._group = None

    def pop_undo(self, task_id: int) -> Step | None:
        """The most recent step for a task, taken off its stack."""
        self.close_group()
        stack = self.undo.get(task_id, [])
        return stack.pop() if stack else None

    def push_redo(self, task_id: int, action: UndoAction) -> None:
        """Remember how to redo what was just undone."""
        self.redo.setdefault(task_id, []).append(action)

    def pop_redo(self, task_id: int) -> UndoAction | None:
        """The most recent undone action for a task, taken off the redo stack."""
        self.close_group()
        stack = self.redo.get(task_id, [])
        return stack.pop() if stack else None

    def push_undo(self, task_id: int, action: UndoAction) -> Step:
        """A redo happened: its opposite goes back on the undo stack (redo stays)."""
        step = Step(task_id, action)
        self.undo.setdefault(task_id, []).append(step)
        return step

    def take_insert(self, block_id: int) -> Step | None:
        """The step that brings back a deleted block (for the toast's Undo), taken out."""
        self.close_group()
        for stack in self.undo.values():
            for index in range(len(stack) - 1, -1, -1):
                action = stack[index].action
                if isinstance(action, InsertBlock) and action.block.id == block_id:
                    return stack.pop(index)
        return None

    def remap(self, old: int, new: int) -> None:
        """A restored block came back with a new ID: point every step at it."""
        for stack in self.undo.values():
            for step in stack:
                step.action = remap_action(step.action, old, new)
        for task_id, actions in self.redo.items():
            self.redo[task_id] = [remap_action(action, old, new) for action in actions]

    def _push(self, task_id: int, action: UndoAction) -> Step:
        self.redo.pop(task_id, None)
        step = Step(task_id, action)
        self.undo.setdefault(task_id, []).append(step)
        return step
