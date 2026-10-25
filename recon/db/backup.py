"""Daily local snapshot of app.db (task 1.5), so "backed up each day" holds from day one.

Uses SQLite's online backup API, which copies a consistent database even while
Recon is writing (a plain file copy could catch a half-written page). The
snapshot is written to a temp file, fsynced and renamed into place, so a
crash never leaves a broken snapshot. The newest 14 are kept.
"""

import logging
import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Final

from recon.db.connection import Database
from recon.errors import StorageError
from recon.logging_setup import Safe
from recon.paths import PRIVATE_FILE_MODE, ensure_private_dir

KEEP: Final = 14
_PREFIX: Final = "app-"

_log = logging.getLogger(__name__)


def snapshot_name(day: date) -> str:
    """File name of a day's snapshot, e.g. app-2026-10-25.db (sorts by date)."""
    return f"{_PREFIX}{day.isoformat()}.db"


def snapshot_if_due(db: Database, folder: Path, today: date, keep: int = KEEP) -> Path | None:
    """Take today's snapshot unless there is one, then keep only the newest `keep`.

    Args:
        db: The live database.
        folder: `backups/db/` in Recon's data folder (created 0700).
        today: Today's date (injected so tests control it).
        keep: How many daily snapshots to keep.

    Returns:
        The new snapshot, or None if today's already existed.

    Raises:
        StorageError: The snapshot couldn't be written (the live database is untouched).
    """
    ensure_private_dir(folder)
    target = folder / snapshot_name(today)
    if target.exists():
        return None
    temp = folder / f".{target.name}.tmp"
    try:
        _write_snapshot(db, temp)
        temp.replace(target)
        _fsync_dir(folder)
    except (OSError, sqlite3.Error) as exc:
        temp.unlink(missing_ok=True)
        _log.error("daily database snapshot failed: %s", Safe(type(exc).__name__))
        raise StorageError from exc
    prune(folder, keep)
    _log.info("daily database snapshot written")
    return target


def prune(folder: Path, keep: int = KEEP) -> list[Path]:
    """Delete all but the newest `keep` snapshots. Returns what was deleted."""
    snapshots = sorted(folder.glob(f"{_PREFIX}????-??-??.db"))
    old = snapshots[: max(0, len(snapshots) - keep)]
    for path in old:
        path.unlink()
    return old


def _write_snapshot(db: Database, temp: Path) -> None:
    temp.unlink(missing_ok=True)
    os.close(os.open(temp, os.O_CREAT | os.O_WRONLY, PRIVATE_FILE_MODE))
    copy = sqlite3.connect(temp)
    try:
        with db.read() as live:
            live.backup(copy)
        # A self-contained file: no -wal sidecar needed to read it.
        copy.execute("PRAGMA journal_mode = DELETE")
    finally:
        copy.close()
    fd = os.open(temp, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(folder: Path) -> None:
    fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
