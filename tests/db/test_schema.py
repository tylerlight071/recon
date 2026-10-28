"""The schema enforces the data model, and the Phase 0 fixture rooms fit it row for row."""

import sqlite3

import pytest

from recon.db.connection import Database
from recon.db.repositories import BlockRepository, RoomRepository, TaskRepository
from recon.errors import StorageError
from tests.fixture_rooms import all_rooms

NOW = "2026-10-25T09:00:00+00:00"


def _room(conn: sqlite3.Connection, **overrides: object) -> int:
    values = {
        "platform": "TryHackMe",
        "name": "R",
        "task_count": 1,
        "created_at": NOW,
        "updated_at": NOW,
    } | overrides
    columns = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    query = f"INSERT INTO rooms ({columns}) VALUES ({marks})"  # noqa: S608 - test-only, fixed keys
    cursor = conn.execute(query, tuple(values.values()))
    return int(cursor.lastrowid or 0)


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "finished"},
        {"mode": "from_scratch"},
        {"task_count": 0},
        {"name": ""},
        {"time_spent_s": -1},
        {"task_count": "three"},  # STRICT tables reject the wrong type
    ],
)
def test_bad_room_rows_are_refused(db: Database, overrides: dict[str, object]) -> None:
    with pytest.raises(StorageError), db.transaction() as conn:
        _room(conn, **overrides)


def test_bad_block_rows_are_refused(db: Database) -> None:
    with db.transaction() as conn:
        room_id = _room(conn)
        task_id = conn.execute(
            "INSERT INTO tasks (room_id, task_index) VALUES (?, 1)", (room_id,)
        ).lastrowid

    bad = [
        ("emoji", 0, '{"text": ""}', "fill"),
        ("key_idea", 0, "not json", "fill"),
        ("key_idea", -1, '{"text": ""}', "fill"),
        ("key_idea", 0, '{"text": ""}', "third"),
    ]
    for block_type, position, content, phase in bad:
        with pytest.raises(StorageError), db.transaction() as conn:
            conn.execute(
                "INSERT INTO blocks (task_id, type, position, content, pass, created_at,"
                " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (task_id, block_type, position, content, phase, NOW, NOW),
            )


def test_foreign_keys_are_enforced(db: Database) -> None:
    with pytest.raises(StorageError), db.transaction() as conn:
        conn.execute("INSERT INTO tasks (room_id, task_index) VALUES (999, 1)")


def _two_tasks_with_one_index(db: Database) -> None:
    with db.transaction() as conn:
        room_id = _room(conn, task_count=2)
        conn.execute("INSERT INTO tasks (room_id, task_index) VALUES (?, 1)", (room_id,))
        conn.execute("INSERT INTO tasks (room_id, task_index) VALUES (?, 1)", (room_id,))


def test_one_task_per_index_in_a_room(db: Database) -> None:
    with pytest.raises(StorageError):
        _two_tasks_with_one_index(db)


def test_deleting_a_room_removes_its_tasks_and_blocks(db: Database) -> None:
    with db.transaction() as conn:
        room_id = _room(conn)
        task_id = conn.execute(
            "INSERT INTO tasks (room_id, task_index) VALUES (?, 1)", (room_id,)
        ).lastrowid
        conn.execute(
            "INSERT INTO blocks (task_id, type, position, content, created_at, updated_at)"
            " VALUES (?, 'key_idea', 0, '{}', ?, ?)",
            (task_id, NOW, NOW),
        )
        conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))

    with db.read() as conn:
        assert conn.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM blocks").fetchone()[0] == 0


def insert_fixture_rooms(db: Database) -> None:
    with db.transaction() as conn:
        for room in all_rooms().values():
            conn.execute(
                "INSERT INTO rooms (id, platform, path, module, name, task_count, mode, status,"
                " created_at, updated_at, time_spent_s, last_task_index)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (room.id, room.platform, room.path, room.module, room.name, room.task_count,
                 room.mode, room.status, room.created_at.isoformat(), room.updated_at.isoformat(),
                 room.time_spent_s, room.last_task_index),
            )  # fmt: skip
            for task in room.tasks:
                conn.execute(
                    "INSERT INTO tasks (id, room_id, task_index, title, status)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (task.id, room.id, task.task_index, task.title, task.status),
                )
                for block in task.blocks:
                    conn.execute(
                        "INSERT INTO blocks (id, task_id, type, position, content, pass,"
                        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (block.id, task.id, block.type, block.position,
                         block.content.model_dump_json(exclude_none=True), block.pass_,
                         block.created_at.isoformat(), block.updated_at.isoformat()),
                    )  # fmt: skip


def test_fixture_rooms_load_and_read_back_exactly(db: Database) -> None:
    insert_fixture_rooms(db)
    rooms, tasks, blocks = RoomRepository(db), TaskRepository(db), BlockRepository(db)

    for fixture in all_rooms().values():
        room = rooms.get(fixture.id)
        assert room is not None
        assert (room.name, room.task_count, room.status) == (
            fixture.name,
            fixture.task_count,
            fixture.status,
        )
        stored_tasks = tasks.for_room(fixture.id)
        assert [t.task_index for t in stored_tasks] == [t.task_index for t in fixture.tasks]
        for stored, original in zip(stored_tasks, fixture.tasks, strict=True):
            got = [(b.type, b.content.text, b.content.answer) for b in blocks.for_task(stored.id)]
            want = [(b.type, b.content.text, b.content.answer) for b in original.blocks]
            assert got == want
