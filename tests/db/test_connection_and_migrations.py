"""Connection pragmas, private files, transactions and migrations."""

import shutil
import sqlite3
import stat
from pathlib import Path

import pytest

from recon.db.connection import Database
from recon.db.migrate import MIGRATIONS_DIR, available, current_version, migrate
from recon.errors import StorageError

TABLES = {"rooms", "tasks", "blocks", "sessions", "settings_kv", "undo_log"}


def _pragma(db: Database, name: str) -> object:
    with db.read() as conn:
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

    assert current_version(db) == len(available()) == 1
    assert tables == TABLES


def test_migrating_twice_changes_nothing(db: Database) -> None:
    assert migrate(db) == 1


def test_database_from_a_newer_recon_is_refused(db: Database) -> None:
    with db.read() as conn:
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
