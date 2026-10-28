"""Connection pragmas, private files, transactions and migrations."""

import shutil
import sqlite3
import stat
from pathlib import Path

import pytest

from recon.db.connection import Database
from recon.db.migrate import MIGRATIONS_DIR, available, current_version, migrate
from recon.errors import StorageError

TABLES = {"rooms", "tasks", "blocks", "sessions", "settings_kv", "undo_log", "sqlite_sequence"}
"""sqlite_sequence is SQLite's own counter table, there since blocks became AUTOINCREMENT (0003)."""


def _pragma(db: Database, name: str) -> object:
    with db.writer() as conn:
        return conn.execute(f"PRAGMA {name}").fetchone()[0]


def test_pragmas(db: Database) -> None:
    assert _pragma(db, "journal_mode") == "wal"
    assert _pragma(db, "foreign_keys") == 1
    assert _pragma(db, "secure_delete") == 1
    assert _pragma(db, "synchronous") == 2  # FULL


def test_database_and_its_wal_files_are_private(db: Database, data_dir: Path) -> None:
    with db.transaction() as conn:
        conn.execute("INSERT INTO settings_kv (key, value) VALUES ('k', 'v')")

    for name in ("app.db", "app.db-wal", "app.db-shm"):
        assert stat.S_IMODE((data_dir / name).stat().st_mode) == 0o600, name


def test_existing_open_database_is_locked_down(data_dir: Path) -> None:
    path = data_dir / "app.db"
    sqlite3.connect(path).close()
    path.chmod(0o644)

    Database.open(path).close()

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_unopenable_database_raises_storage_error(data_dir: Path) -> None:
    (data_dir / "app.db").mkdir()

    with pytest.raises(StorageError):
        Database.open(data_dir / "app.db")


def _insert_twice(db: Database) -> None:
    with db.transaction() as conn:
        conn.execute("INSERT INTO settings_kv (key, value) VALUES ('a', '1')")
        conn.execute("INSERT INTO settings_kv (key, value) VALUES ('a', '2')")  # duplicate key


def _insert_then_fail(db: Database) -> None:
    with db.transaction() as conn:
        conn.execute("INSERT INTO settings_kv (key, value) VALUES ('a', '1')")
        raise KeyError


def test_failed_write_rolls_back(db: Database) -> None:
    with pytest.raises(StorageError):
        _insert_twice(db)

    with db.read() as conn:
        assert conn.execute("SELECT count(*) FROM settings_kv").fetchone()[0] == 0


def test_other_errors_roll_back_and_propagate(db: Database) -> None:
    with pytest.raises(KeyError):
        _insert_then_fail(db)

    with db.read() as conn:
        assert conn.execute("SELECT count(*) FROM settings_kv").fetchone()[0] == 0


def test_fresh_database_migrates_to_the_latest_schema(db: Database) -> None:
    with db.read() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    assert current_version(db) == len(available()) == 3
    assert tables == TABLES


def test_migrating_twice_changes_nothing(db: Database) -> None:
    assert migrate(db) == 3


def test_database_from_a_newer_recon_is_refused(db: Database) -> None:
    with db.writer() as conn:
        conn.execute("PRAGMA user_version = 99")

    with pytest.raises(StorageError):
        migrate(db)


def test_misnumbered_migrations_are_refused(tmp_path: Path) -> None:
    shutil.copy(MIGRATIONS_DIR / "0001_initial.sql", tmp_path / "0001_initial.sql")
    (tmp_path / "0003_skipped.sql").write_text("SELECT 1;")

    with pytest.raises(StorageError):
        available(tmp_path)


def test_failing_migration_is_rolled_back_whole(data_dir: Path, tmp_path: Path) -> None:
    folder = tmp_path / "migrations"
    folder.mkdir()
    shutil.copy(MIGRATIONS_DIR / "0001_initial.sql", folder / "0001_initial.sql")
    (folder / "0002_broken.sql").write_text(
        "CREATE TABLE half_done (id INTEGER PRIMARY KEY);\nTHIS IS NOT SQL;\n"
    )
    db = Database.open(data_dir / "app.db")

    with pytest.raises(StorageError):
        migrate(db, folder)

    assert current_version(db) == 1
    with db.read() as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "half_done" not in names
    db.close()


def test_migration_files_are_numbered_from_one() -> None:
    assert [m.version for m in available()] == list(range(1, len(available()) + 1))
    assert available()[0].path.name == "0001_initial.sql"


def test_0002_adds_task_time_to_a_version_1_database_with_rooms(
    data_dir: Path, tmp_path: Path
) -> None:
    folder = tmp_path / "v1"
    folder.mkdir()
    shutil.copy(MIGRATIONS_DIR / "0001_initial.sql", folder / "0001_initial.sql")
    db = Database.open(data_dir / "app.db")
    migrate(db, folder)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO rooms (platform, path, module, name, task_count, mode, created_at,"
            " updated_at, time_spent_s) VALUES ('TryHackMe', '', '', 'Old room', 2, 'new',"
            " '2026-10-01T09:00:00+00:00', '2026-10-01T09:00:00+00:00', 600)"
        )
        conn.executemany(
            "INSERT INTO tasks (room_id, task_index, title, status) VALUES (1, ?, ?, 'done')",
            [(1, "First"), (2, "Second")],
        )

    assert migrate(db) == 3

    with db.read() as conn:
        rows = conn.execute("SELECT title, status, time_spent_s FROM tasks ORDER BY id").fetchall()
        room = conn.execute("SELECT name, time_spent_s FROM rooms").fetchone()
    assert rows == [("First", "done", 0), ("Second", "done", 0)]
    assert room == ("Old room", 600)
    with pytest.raises(StorageError), db.transaction() as conn:
        conn.execute("UPDATE tasks SET time_spent_s = -1")
    db.close()


def test_0003_keeps_blocks_and_never_reuses_an_id_undo_remembers(
    data_dir: Path, tmp_path: Path
) -> None:
    folder = tmp_path / "v2"
    folder.mkdir()
    for name in ("0001_initial.sql", "0002_task_time.sql"):
        shutil.copy(MIGRATIONS_DIR / name, folder / name)
    db = Database.open(data_dir / "app.db")
    migrate(db, folder)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO rooms (platform, path, module, name, task_count, mode, created_at,"
            " updated_at) VALUES ('TryHackMe', '', '', 'Old room', 1, 'new', 'x', 'x')"
        )
        conn.execute("INSERT INTO tasks (room_id, task_index) VALUES (1, 1)")
        conn.executemany(
            "INSERT INTO blocks (id, task_id, type, position, content, created_at, updated_at)"
            " VALUES (?, 1, 'key_idea', ?, ?, 'x', 'x')",
            [(1, 0, '{"text": "one"}'), (4, 1, '{"text": "four"}')],
        )
        # A deleted block 7 that Undo could still bring back.
        conn.execute(
            "INSERT INTO undo_log (entity, entity_id, before, created_at)"
            " VALUES ('insert_block', 7, '{}', 'x')"
        )

    assert migrate(db) == 3

    with db.transaction() as conn:
        rows = conn.execute("SELECT id, json_extract(content, '$.text') FROM blocks").fetchall()
        conn.execute(
            "INSERT INTO blocks (task_id, type, position, content, created_at, updated_at)"
            " VALUES (1, 'key_idea', 2, '{}', 'x', 'x')"
        )
        new_id = conn.execute("SELECT max(id) FROM blocks").fetchone()[0]
        index = conn.execute("SELECT name FROM sqlite_master WHERE name = 'blocks_by_task'")
        assert index.fetchone() is not None
    assert rows == [(1, "one"), (4, "four")]
    assert new_id == 8
    db.close()


def test_0003_on_an_empty_database_starts_ids_at_one(db: Database) -> None:
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO rooms (platform, path, module, name, task_count, mode, created_at,"
            " updated_at) VALUES ('TryHackMe', '', '', 'R', 1, 'new', 'x', 'x')"
        )
        conn.execute("INSERT INTO tasks (room_id, task_index) VALUES (1, 1)")
        conn.execute(
            "INSERT INTO blocks (task_id, type, position, content, created_at, updated_at)"
            " VALUES (1, 'key_idea', 0, '{}', 'x', 'x')"
        )
        assert conn.execute("SELECT max(id) FROM blocks").fetchone()[0] == 1


def test_reads_use_a_read_only_connection_that_never_waits_for_a_writer(db: Database) -> None:
    # Audit F-05: a read used to wait behind the writer's lock for a whole commit.
    import threading  # noqa: PLC0415 - only this test needs it
    import time  # noqa: PLC0415

    with db.read() as conn:
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE nope (x)")

    entered = threading.Event()
    release = threading.Event()

    def slow_write() -> None:
        with db.transaction() as conn:
            conn.execute("INSERT INTO settings_kv (key, value) VALUES ('k', 'v')")
            entered.set()
            release.wait(2)

    writer = threading.Thread(target=slow_write)
    writer.start()
    assert entered.wait(2)
    started = time.monotonic()
    with db.read() as conn:
        conn.execute("SELECT count(*) FROM rooms").fetchone()
    waited = time.monotonic() - started
    release.set()
    writer.join()

    assert waited < 0.1
    with db.read() as conn:  # and once committed, the reader sees it
        assert conn.execute("SELECT value FROM settings_kv").fetchone() == ("v",)
