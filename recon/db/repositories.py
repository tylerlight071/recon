"""Repositories for rooms, tasks and blocks. Parameterised SQL only; models out.

Every query is a complete literal (no SQL built from strings), so nothing
The user types can change a query's shape. Every text field passes through the
flag filter here, the last stop before the database (hard rule 2), so no
caller can store a flag by forgetting to filter. Every change to a room's tasks or
blocks also bumps the room's `updated_at`, which "recent rooms" and
"Where was I?" sort by.
"""

import json
import sqlite3
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Final

from recon.db.connection import Database
from recon.db.models import (
    Block,
    BlockContent,
    BlockPass,
    BlockType,
    InsertBlock,
    NewRoom,
    Room,
    RoomStatus,
    SetContent,
    Task,
    TaskStatus,
    UndoAction,
    UndoEntry,
    action_block_id,
)
from recon.engine.flags_filter import LONE_HEX, strip_flags
from recon.errors import StorageError

type Clock = Callable[[], datetime]

_ROOM_FIELDS: Final = (
    "id", "platform", "path", "module", "name", "task_count", "mode", "status",
    "created_at", "updated_at", "time_spent_s", "last_task_index",
)  # fmt: skip
_BLOCK_FIELDS: Final = (
    "id", "task_id", "type", "position", "content", "pass", "created_at", "updated_at",
)  # fmt: skip

_SELECT_ROOM: Final = """
    SELECT id, platform, path, module, name, task_count, mode, status,
           created_at, updated_at, time_spent_s, last_task_index
    FROM rooms WHERE id = ?"""
_SELECT_RECENT_ROOMS: Final = """
    SELECT id, platform, path, module, name, task_count, mode, status,
           created_at, updated_at, time_spent_s, last_task_index
    FROM rooms ORDER BY updated_at DESC, id DESC LIMIT ?"""
_SELECT_CURRENT_ROOM: Final = """
    SELECT id, platform, path, module, name, task_count, mode, status,
           created_at, updated_at, time_spent_s, last_task_index
    FROM rooms WHERE status = 'capturing' ORDER BY updated_at DESC, id DESC LIMIT 1"""
_SELECT_WAITING_ROOMS: Final = """
    SELECT id, platform, path, module, name, task_count, mode, status,
           created_at, updated_at, time_spent_s, last_task_index
    FROM rooms WHERE status IN ('queued', 'processing') ORDER BY updated_at, id"""
_INSERT_ROOM: Final = """
    INSERT INTO rooms (platform, path, module, name, task_count, mode, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
_UPDATE_PROGRESS: Final = """
    UPDATE rooms SET last_task_index = coalesce(?, last_task_index),
                     time_spent_s = time_spent_s + ?,
                     status = coalesce(?, status),
                     updated_at = ?
    WHERE id = ?"""
_INSERT_TASK: Final = "INSERT INTO tasks (room_id, task_index) VALUES (?, ?)"
_SELECT_TASKS: Final = """
    SELECT id, room_id, task_index, title, status, time_spent_s
    FROM tasks WHERE room_id = ? ORDER BY task_index"""
_ADD_TASK_TIME: Final = "UPDATE tasks SET time_spent_s = time_spent_s + ? WHERE id = ?"
_ADD_ROOM_TIME_OF_TASK: Final = """
    UPDATE rooms SET time_spent_s = time_spent_s + ?
    WHERE id = (SELECT room_id FROM tasks WHERE id = ?)"""
_SET_TASK_TITLE: Final = "UPDATE tasks SET title = ? WHERE id = ?"
_SET_TASK_STATUS: Final = "UPDATE tasks SET status = ? WHERE id = ?"
_TOUCH_ROOM_OF_TASK: Final = (
    "UPDATE rooms SET updated_at = ? WHERE id = (SELECT room_id FROM tasks WHERE id = ?)"
)
_TOUCH_ROOM_OF_BLOCK: Final = """
    UPDATE rooms SET updated_at = ? WHERE id =
        (SELECT t.room_id FROM tasks t JOIN blocks b ON b.task_id = t.id WHERE b.id = ?)"""
_SELECT_BLOCKS: Final = """
    SELECT id, task_id, type, position, content, pass, created_at, updated_at
    FROM blocks WHERE task_id = ? ORDER BY position, id"""
_SELECT_BLOCK: Final = """
    SELECT id, task_id, type, position, content, pass, created_at, updated_at
    FROM blocks WHERE id = ?"""
_SELECT_BLOCK_IDS: Final = "SELECT id FROM blocks WHERE task_id = ? ORDER BY position, id"
_SELECT_BLOCK_TASK: Final = "SELECT task_id FROM blocks WHERE id = ?"
_COUNT_BLOCKS: Final = "SELECT count(*) FROM blocks WHERE task_id = ?"
_INSERT_BLOCK: Final = """
    INSERT INTO blocks (task_id, type, position, content, pass, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)"""
_UPDATE_BLOCK_CONTENT: Final = "UPDATE blocks SET content = ?, updated_at = ? WHERE id = ?"
_SET_BLOCK_POSITION: Final = "UPDATE blocks SET position = ? WHERE id = ?"
_DELETE_BLOCK: Final = "DELETE FROM blocks WHERE id = ?"
_BLOCK_EXISTS: Final = "SELECT 1 FROM blocks WHERE id = ?"
_RESTORE_BLOCK: Final = """
    INSERT INTO blocks (id, task_id, type, position, content, pass, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
_INSERT_UNDO: Final = """
    INSERT INTO undo_log (entity, entity_id, before, created_at) VALUES (?, ?, ?, ?)"""
_SELECT_UNDO: Final = """
    SELECT id, before FROM undo_log
    WHERE json_extract(before, '$.room_id') = ? ORDER BY id"""
_UPDATE_UNDO: Final = "UPDATE undo_log SET entity_id = ?, before = ? WHERE id = ?"
_DELETE_UNDO: Final = "DELETE FROM undo_log WHERE id = ?"
_CLEAR_UNDO: Final = "DELETE FROM undo_log WHERE json_extract(before, '$.room_id') = ?"
_EXPIRE_UNDO: Final = "DELETE FROM undo_log WHERE created_at < ?"
_PRUNE_UNDO: Final = """
    DELETE FROM undo_log WHERE json_extract(before, '$.room_id') = ? AND id NOT IN (
        SELECT id FROM undo_log WHERE json_extract(before, '$.room_id') = ?
        ORDER BY id DESC LIMIT ?)"""
_SELECT_LATEST_WRITTEN: Final = """
    SELECT b.id, b.task_id, b.type, b.position, b.content, b.pass, b.created_at, b.updated_at
    FROM blocks b JOIN tasks t ON t.id = b.task_id
    WHERE t.room_id = ? AND trim(json_extract(b.content, '$.text')) != ''
    ORDER BY b.updated_at DESC, b.id DESC LIMIT 1"""


def clean_text(text: str) -> str:
    """Text with every flag removed, finished or not (no exceptions: names, titles)."""
    return strip_flags(text, unfinished=True).text


def clean_content(content: BlockContent, *, typing: bool = False) -> BlockContent:
    """Block content with flags removed (finished or not), except hex strings the user kept.

    `typing` (timed autosaves, undo snapshots) also holds back a hash still being typed.
    """
    kept = set(content.kept)
    text = strip_flags(content.text, kept, unfinished=True, typing=typing).text
    answer = (
        None
        if content.answer is None
        else strip_flags(content.answer, kept, unfinished=True, typing=typing).text
    )
    return content.model_copy(update={"text": text, "answer": answer})


def utc_now() -> datetime:
    """The real clock (tests pass their own)."""
    return datetime.now(UTC)


def _room(row: Sequence[object]) -> Room:
    return Room.model_validate(dict(zip(_ROOM_FIELDS, row, strict=True)))


def _block(row: Sequence[object]) -> Block:
    data = dict(zip(_BLOCK_FIELDS, row, strict=True))
    data["content"] = BlockContent.model_validate_json(str(data["content"]))
    return Block.model_validate(data)


def _inserted_id(cursor: sqlite3.Cursor) -> int:
    if cursor.lastrowid is None:  # SQLite always sets it after an INSERT
        raise StorageError
    return cursor.lastrowid


class RoomRepository:
    """Rooms (and the tasks a new room starts with)."""

    def __init__(self, db: Database, clock: Clock = utc_now) -> None:
        """Use `db`; `clock` stamps created_at/updated_at."""
        self._db = db
        self._clock = clock

    def create(self, new: NewRoom) -> Room:
        """Insert a room and its tasks (1..task_count) in one transaction."""
        now = self._clock().isoformat()
        with self._db.transaction() as conn:
            cursor = conn.execute(
                _INSERT_ROOM,
                (
                    clean_text(new.platform),
                    clean_text(new.path),
                    clean_text(new.module),
                    clean_text(new.name) or "Untitled room",
                    new.task_count,
                    new.mode,
                    now,
                    now,
                ),
            )
            room_id = _inserted_id(cursor)
            conn.executemany(
                _INSERT_TASK, [(room_id, index) for index in range(1, new.task_count + 1)]
            )
        return self._get_existing(room_id)

    def get(self, room_id: int) -> Room | None:
        """The room, or None."""
        with self._db.read() as conn:
            row = conn.execute(_SELECT_ROOM, (room_id,)).fetchone()
        return _room(row) if row else None

    def recent(self, limit: int = 10) -> list[Room]:
        """Rooms, most recently touched first."""
        with self._db.read() as conn:
            rows = conn.execute(_SELECT_RECENT_ROOMS, (limit,)).fetchall()
        return [_room(row) for row in rows]

    def current(self) -> Room | None:
        """The room the user is in the middle of: the most recently touched one still capturing."""
        with self._db.read() as conn:
            row = conn.execute(_SELECT_CURRENT_ROOM).fetchone()
        return _room(row) if row else None

    def waiting(self) -> list[Room]:
        """Rooms finished but not yet processed (queued, or cut off mid-run), oldest first."""
        with self._db.read() as conn:
            rows = conn.execute(_SELECT_WAITING_ROOMS).fetchall()
        return [_room(row) for row in rows]

    def update_progress(
        self,
        room_id: int,
        *,
        last_task_index: int | None = None,
        add_time_s: int = 0,
        status: RoomStatus | None = None,
    ) -> bool:
        """Record where the user is, time spent and status.

        Returns:
            Whether the room exists.
        """
        stamp = self._clock().isoformat()
        with self._db.transaction() as conn:
            cursor = conn.execute(
                _UPDATE_PROGRESS, (last_task_index, add_time_s, status, stamp, room_id)
            )
        return cursor.rowcount == 1

    def _get_existing(self, room_id: int) -> Room:
        room = self.get(room_id)
        if room is None:  # just committed, so only a broken database gets here
            raise StorageError
        return room


class TaskRepository:
    """A room's tasks."""

    def __init__(self, db: Database, clock: Clock = utc_now) -> None:
        """Use `db`; `clock` stamps the room's updated_at."""
        self._db = db
        self._clock = clock

    def for_room(self, room_id: int) -> list[Task]:
        """The room's tasks in order."""
        with self._db.read() as conn:
            rows = conn.execute(_SELECT_TASKS, (room_id,)).fetchall()
        return [
            Task(id=r[0], room_id=r[1], task_index=r[2], title=r[3], status=r[4], time_spent_s=r[5])
            for r in rows
        ]

    def set_title(self, task_id: int, title: str) -> bool:
        """Rename a task ("" means the default "Task n"). Returns whether it exists."""
        return self._update(_SET_TASK_TITLE, task_id, clean_text(title))

    def set_status(self, task_id: int, status: TaskStatus) -> bool:
        """Mark a task open, done or skipped. Returns whether it exists."""
        return self._update(_SET_TASK_STATUS, task_id, status)

    def add_time(self, task_id: int, seconds: int) -> bool:
        """Record time spent on a task, and on its room.

        Doesn't touch the room's `updated_at`: "Where was I?" means the last note,
        not the last tick of the clock.

        Returns:
            Whether the task exists.
        """
        if seconds <= 0:
            return False
        with self._db.transaction() as conn:
            cursor = conn.execute(_ADD_TASK_TIME, (seconds, task_id))
            conn.execute(_ADD_ROOM_TIME_OF_TASK, (seconds, task_id))
        return cursor.rowcount == 1

    def _update(self, query: str, task_id: int, value: str) -> bool:
        with self._db.transaction() as conn:
            cursor = conn.execute(query, (value, task_id))
            conn.execute(_TOUCH_ROOM_OF_TASK, (self._clock().isoformat(), task_id))
        return cursor.rowcount == 1


class BlockRepository:
    """A task's blocks: add, edit, move, delete. Positions stay 0..n-1."""

    def __init__(self, db: Database, clock: Clock = utc_now) -> None:
        """Use `db`; `clock` stamps created_at/updated_at."""
        self._db = db
        self._clock = clock

    def for_task(self, task_id: int) -> list[Block]:
        """The task's blocks in order."""
        with self._db.read() as conn:
            rows = conn.execute(_SELECT_BLOCKS, (task_id,)).fetchall()
        return [_block(row) for row in rows]

    def get(self, block_id: int) -> Block | None:
        """The block, or None."""
        with self._db.read() as conn:
            row = conn.execute(_SELECT_BLOCK, (block_id,)).fetchone()
        return _block(row) if row else None

    def add(
        self,
        task_id: int,
        block_type: BlockType,
        content: BlockContent | None = None,
        phase: BlockPass = "fill",
    ) -> Block:
        """Append a block to the end of a task.

        Args:
            task_id: The task.
            block_type: Which kind of block.
            content: Initial content (empty by default).
            phase: "recall" in From memory's first pass, otherwise "fill".

        Returns:
            The new block.
        """
        now = self._clock().isoformat()
        body = clean_content(content or BlockContent()).model_dump_json()
        with self._db.transaction() as conn:
            position = conn.execute(_COUNT_BLOCKS, (task_id,)).fetchone()[0]
            cursor = conn.execute(
                _INSERT_BLOCK, (task_id, block_type, position, body, phase, now, now)
            )
            block_id = _inserted_id(cursor)
            conn.execute(_TOUCH_ROOM_OF_TASK, (now, task_id))
        block = self.get(block_id)
        if block is None:  # just committed, so only a broken database gets here
            raise StorageError
        return block

    def latest_written(self, room_id: int) -> Block | None:
        """The room's most recently edited block that has text (for "Last note")."""
        with self._db.read() as conn:
            row = conn.execute(_SELECT_LATEST_WRITTEN, (room_id,)).fetchone()
        return _block(row) if row else None

    def ensure_starter_block(self, task_id: int, phase: BlockPass = "fill") -> Block:
        """Never a blank page: give an empty task its first, empty Key idea block."""
        existing = self.for_task(task_id)
        return existing[0] if existing else self.add(task_id, "key_idea", phase=phase)

    def update_content(self, block_id: int, content: BlockContent, final: bool = True) -> bool:
        """Save a block's content (what autosave calls). Returns whether it exists.

        `final` is False for timed autosaves while the user types: a hash still being
        typed at a line's end is held back until the next save (audit F-07).
        """
        now = self._clock().isoformat()
        body = clean_content(content, typing=not final).model_dump_json()
        with self._db.transaction() as conn:
            cursor = conn.execute(_UPDATE_BLOCK_CONTENT, (body, now, block_id))
            conn.execute(_TOUCH_ROOM_OF_BLOCK, (now, block_id))
        return cursor.rowcount == 1

    def keep_lookalike(self, block_id: int, text: str) -> bool:
        """Record "Not a flag, keep it" for one hex string in a block.

        Only lone hex strings (an example hash) can be kept; THM{...},
        flag{...} and HTB{...} never can (hard rule 2).

        Returns:
            Whether it was recorded (the block exists and the text is a hex lookalike).
        """
        block = self.get(block_id)
        if block is None or LONE_HEX.fullmatch(text) is None:
            return False
        if text in block.content.kept:
            return True
        kept = (*block.content.kept, text)
        return self.update_content(block_id, block.content.model_copy(update={"kept": kept}))

    def restore(self, block: Block) -> Block:
        """Put a deleted block back at its old place and with its own ID (Undo).

        IDs are never reused (migration 0003), so the old ID is always free.

        Returns:
            The block as stored.

        Raises:
            StorageError: The ID is taken (only a database edited by hand gets here).
        """
        now = self._clock().isoformat()
        body = clean_content(block.content).model_dump_json()
        with self._db.transaction() as conn:
            if conn.execute(_BLOCK_EXISTS, (block.id,)).fetchone() is not None:
                raise StorageError
            ids = [r[0] for r in conn.execute(_SELECT_BLOCK_IDS, (block.task_id,))]
            cursor = conn.execute(
                _RESTORE_BLOCK,
                (
                    block.id,
                    block.task_id,
                    block.type,
                    len(ids),
                    body,
                    block.phase,
                    block.created_at.isoformat(),
                    now,
                ),
            )
            block_id = _inserted_id(cursor)
            ids.insert(max(0, min(block.position, len(ids))), block_id)
            _renumber(conn, ids)
            conn.execute(_TOUCH_ROOM_OF_TASK, (now, block.task_id))
        restored = self.get(block_id)
        if restored is None:  # just committed, so only a broken database gets here
            raise StorageError
        return restored

    def move(self, block_id: int, new_position: int) -> bool:
        """Move a block within its task; the others close up around it.

        Returns:
            Whether the block exists.
        """
        with self._db.transaction() as conn:
            row = conn.execute(_SELECT_BLOCK_TASK, (block_id,)).fetchone()
            if row is None:
                return False
            ids = [r[0] for r in conn.execute(_SELECT_BLOCK_IDS, (row[0],))]
            ids.remove(block_id)
            ids.insert(max(0, min(new_position, len(ids))), block_id)
            _renumber(conn, ids)
            conn.execute(_TOUCH_ROOM_OF_TASK, (self._clock().isoformat(), row[0]))
        return True

    def delete(self, block_id: int) -> Block | None:
        """Delete a block and close the gap.

        Returns:
            The deleted block (for Undo, task 1.11), or None if it didn't exist.
        """
        block = self.get(block_id)
        if block is None:
            return None
        with self._db.transaction() as conn:
            conn.execute(_DELETE_BLOCK, (block_id,))
            _renumber(conn, [r[0] for r in conn.execute(_SELECT_BLOCK_IDS, (block.task_id,))])
            conn.execute(_TOUCH_ROOM_OF_TASK, (self._clock().isoformat(), block.task_id))
        return block


def _renumber(conn: sqlite3.Connection, ids: list[int]) -> None:
    conn.executemany(_SET_BLOCK_POSITION, [(i, block_id) for i, block_id in enumerate(ids)])


def _clean_action(action: UndoAction) -> UndoAction:
    # Undo history is stored text too: flags never reach it (hard rule 2).
    if isinstance(action, SetContent):
        return action.model_copy(update={"content": clean_content(action.content, typing=True)})
    if isinstance(action, InsertBlock):
        cleaned = clean_content(action.block.content, typing=True)
        block = action.block.model_copy(update={"content": cleaned})
        return action.model_copy(update={"block": block})
    return action


def _undo_body(room_id: int, task_id: int, action: UndoAction) -> str:
    return json.dumps(
        {
            "room_id": room_id,
            "task_id": task_id,
            "action": action.model_dump(mode="json", by_alias=True),
        }
    )


class UndoRepository:
    """The `undo_log`: steps back for each task, kept across restarts."""

    KEEP_PER_ROOM: Final = 300
    """Older steps are dropped when a room opens."""
    KEEP_DAYS: Final = 30
    """Steps (and the old text they hold) go after this long, whichever room."""

    def __init__(self, db: Database, clock: Clock = utc_now) -> None:
        """Use `db`; `clock` stamps created_at."""
        self._db = db
        self._clock = clock

    def push(self, room_id: int, task_id: int, action: UndoAction) -> UndoEntry:
        """Record a step back (flags stripped) and return it with its ID."""
        action = _clean_action(action)
        with self._db.transaction() as conn:
            cursor = conn.execute(
                _INSERT_UNDO,
                (
                    action.kind,
                    action_block_id(action),
                    _undo_body(room_id, task_id, action),
                    self._clock().isoformat(),
                ),
            )
        return UndoEntry(id=_inserted_id(cursor), room_id=room_id, task_id=task_id, action=action)

    def for_room(self, room_id: int) -> list[UndoEntry]:
        """The room's steps back, oldest first, after dropping all but the newest few hundred."""
        cutoff = (self._clock() - timedelta(days=self.KEEP_DAYS)).isoformat()
        with self._db.transaction() as conn:
            conn.execute(_EXPIRE_UNDO, (cutoff,))
            conn.execute(_PRUNE_UNDO, (room_id, room_id, self.KEEP_PER_ROOM))
            rows = conn.execute(_SELECT_UNDO, (room_id,)).fetchall()
        return [UndoEntry.model_validate({"id": row[0], **json.loads(row[1])}) for row in rows]

    def delete(self, entry_id: int) -> None:
        """Forget a step (it was taken)."""
        with self._db.transaction() as conn:
            conn.execute(_DELETE_UNDO, (entry_id,))

    def clear_room(self, room_id: int) -> None:
        """Forget a room's steps, and the deleted or overwritten text they hold (room finished)."""
        with self._db.transaction() as conn:
            conn.execute(_CLEAR_UNDO, (room_id,))
