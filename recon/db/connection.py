"""The SQLite connections to `app.db` (CLAUDE.md, Data safety).

One writer: every write goes through a single connection guarded by a lock,
so the autosave thread and the room worker never write at the same time.
Reads use a second connection with `query_only` set, under its own lock: in
WAL mode a reader sees the last commit without waiting for a writer, so a read
on the UI thread never sits behind a commit's fsync (audit F-05).
WAL mode and full sync mean a crash or `kill -9` keeps every committed write;
`secure_delete` overwrites deleted note text instead of leaving it on disk.
"""

import logging
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final, Self

from recon.errors import StorageError
from recon.logging_setup import Safe
from recon.paths import PRIVATE_FILE_MODE, ensure_private_file

PRAGMAS: Final = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = FULL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA secure_delete = ON",
    "PRAGMA busy_timeout = 5000",
)

_log = logging.getLogger(__name__)


class Database:
    """Owns the writer and reader connections; hands each out under its own lock."""

    def __init__(
        self, connection: sqlite3.Connection, reader: sqlite3.Connection | None = None
    ) -> None:
        """Wrap open connections (use `Database.open` to create them).

        Args:
            connection: The writer.
            reader: A read-only connection; without one, reads share the writer.
        """
        self._conn = connection
        self._lock = threading.RLock()
        self._reader = reader or connection
        self._read_lock = threading.RLock() if reader is not None else self._lock

    @classmethod
    def open(cls, path: Path) -> Self:
        """Open (or create) the database privately with Recon's pragmas.

        Args:
            path: `app.db`; its folder must exist with private permissions.

        Returns:
            The database.

        Raises:
            StorageError: It couldn't be opened, or WAL mode wasn't accepted.
        """
        try:
            if not path.exists():
                # Create it 0600 ourselves; SQLite gives -wal/-shm the same mode.
                os.close(os.open(path, os.O_CREAT | os.O_WRONLY, PRIVATE_FILE_MODE))
            ensure_private_file(path)
            connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
            for pragma in PRAGMAS:
                connection.execute(pragma)
            mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            if mode != "wal":
                connection.close()
                raise StorageError
            reader = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
            reader.execute("PRAGMA busy_timeout = 5000")
            reader.execute("PRAGMA query_only = ON")
        except (OSError, sqlite3.Error) as exc:
            _log.error("database open failed: %s", Safe(type(exc).__name__))
            raise StorageError from exc
        return cls(connection, reader)

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """The read-only connection. Never waits for a write in progress."""
        with self._read_lock:
            yield self._reader

    @contextmanager
    def writer(self) -> Iterator[sqlite3.Connection]:
        """The writer itself, under its lock, for statements that run their own transaction.

        For migration scripts and checkpoints; use `transaction()` for everything else.
        """
        with self._lock:
            yield self._conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """A write transaction: committed on success, rolled back on any error.

        Raises:
            StorageError: SQLite refused the write (the transaction is rolled back).
        """
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except sqlite3.Error as exc:
                self._conn.execute("ROLLBACK")
                _log.error("database write failed: %s", Safe(type(exc).__name__))
                raise StorageError from exc
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    def close(self) -> None:
        """Close both connections; the writer goes last, checkpointing the WAL."""
        with self._read_lock:
            if self._reader is not self._conn:
                self._reader.close()
        with self._lock:
            self._conn.close()
