"""Numbered schema migrations (`migrations/NNNN_name.sql`), tracked in `PRAGMA user_version`."""

import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from recon.db.connection import Database
from recon.errors import DatabaseTooNewError, StorageError
from recon.logging_setup import Safe

MIGRATIONS_DIR: Final = Path(__file__).resolve().parent / "migrations"
_NAME: Final = re.compile(r"(\d{4})_[a-z0-9_]+\.sql")

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Migration:
    """One schema step."""

    version: int
    path: Path

    @property
    def sql(self) -> str:
        """The migration's SQL."""
        return self.path.read_text(encoding="utf-8")


def available(folder: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Every migration file in version order.

    Raises:
        StorageError: The numbering has a gap or a duplicate (a packaging mistake).
    """
    found = sorted(
        (
            Migration(int(match.group(1)), path)
            for path in folder.glob("*.sql")
            if (match := _NAME.fullmatch(path.name))
        ),
        key=lambda migration: migration.version,
    )
    if [m.version for m in found] != list(range(1, len(found) + 1)):
        _log.error("migration files are misnumbered")
        raise StorageError
    return found


def current_version(db: Database) -> int:
    """The schema version the database is at (0 for a new one)."""
    with db.read() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    return int(version)


def migrate(db: Database, folder: Path = MIGRATIONS_DIR) -> int:
    """Apply every migration the database hasn't had, each in its own transaction.

    Args:
        db: The database.
        folder: Where the migration files are (tests pass their own).

    Returns:
        The schema version afterwards.

    Raises:
        StorageError: A migration failed (that step is rolled back), or the
            database is newer than this version of Recon knows (DatabaseTooNewError).
    """
    migrations = available(folder)
    version = current_version(db)
    latest = migrations[-1].version if migrations else 0
    if version > latest:
        _log.error("database schema %s is newer than this recon (%s)", version, latest)
        raise DatabaseTooNewError
    for migration in migrations[version:]:
        _apply(db, migration)
    return current_version(db)


def _apply(db: Database, migration: Migration) -> None:
    # executescript() commits any open transaction first, so the BEGIN, the
    # schema and the version bump all go in one script; on error, roll back.
    script = (
        f"BEGIN IMMEDIATE;\n{migration.sql}\nPRAGMA user_version = {migration.version};\nCOMMIT;\n"
    )
    with db.writer() as conn:
        try:
            conn.executescript(script)
        except sqlite3.Error as exc:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            _log.error("migration %s failed: %s", migration.version, Safe(type(exc).__name__))
            raise StorageError from exc
    _log.info("migrated database to schema %s", migration.version)
