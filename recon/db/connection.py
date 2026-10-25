"""The one SQLite connection to `app.db` (CLAUDE.md, Data safety).

One writer: every read and write goes through a single connection guarded by
a lock, so the autosave thread and the UI never write at the same time.
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
    """Owns the connection; hands it out under a lock for reads and transactions."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Wrap an open connection (use `Database.open` to create one)."""
        self._conn = connection
        self._lock = threading.RLock()

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
        except (OSError, sqlite3.Error) as exc:
            _log.error("database open failed: %s", Safe(type(exc).__name__))
            raise StorageError from exc
        if mode != "wal":
            connection.close()
            raise StorageError
        return cls(connection)

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """The connection, for reads, while holding the lock."""
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
        """Close the connection (checkpointing the WAL into the main file)."""
        with self._lock:
            self._conn.close()
