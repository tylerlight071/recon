"""Processing runs in `app.db` (task 2.4): staged, then applied or discarded.

A run's files live in `runs/<run id>/` and its backups in `backups/<run id>/`;
this table records what happened, for Library's History (task 2.8) and for
finishing an Apply that a crash interrupted.
"""

from collections.abc import Sequence
from typing import Final

from recon.db.connection import Database
from recon.db.models import Run
from recon.db.repositories import Clock, utc_now
from recon.errors import StorageError

_FIELDS: Final = ("id", "room_id", "status", "created_at", "finished_at", "written", "backed_up")
_SELECT_RUN: Final = """
SELECT id, room_id, status, created_at, finished_at, written, backed_up FROM runs WHERE id = ?
"""
_SELECT_FOR_ROOM: Final = """
SELECT id, room_id, status, created_at, finished_at, written, backed_up FROM runs
WHERE room_id = ? ORDER BY created_at DESC, id DESC
"""
_SELECT_STAGED: Final = """
SELECT id, room_id, status, created_at, finished_at, written, backed_up FROM runs
WHERE status = 'staged' ORDER BY created_at, id
"""
_INSERT_RUN: Final = "INSERT INTO runs (id, room_id, created_at) VALUES (?, ?, ?)"
_FINISH_RUN: Final = """
UPDATE runs SET status = ?, finished_at = ?, written = ?, backed_up = ?
WHERE id = ? AND status = 'staged'
"""


def _run(row: Sequence[object]) -> Run:
    return Run.model_validate(dict(zip(_FIELDS, row, strict=True)))


class RunRepository:
    """Records each run: staged when its notes are ready, then applied or discarded."""

    def __init__(self, db: Database, clock: Clock = utc_now) -> None:
        """Use `db`; `clock` stamps when runs start and finish."""
        self._db = db
        self._clock = clock

    def start(self, run_id: str, room_id: int) -> Run:
        """Record a newly staged run."""
        with self._db.transaction() as conn:
            conn.execute(_INSERT_RUN, (run_id, room_id, self._clock().isoformat()))
        run = self.get(run_id)
        if run is None:  # just committed, so only a broken database gets here
            raise StorageError
        return run

    def get(self, run_id: str) -> Run | None:
        """The run, or None."""
        with self._db.read() as conn:
            row = conn.execute(_SELECT_RUN, (run_id,)).fetchone()
        return _run(row) if row else None

    def for_room(self, room_id: int) -> list[Run]:
        """A room's runs, newest first."""
        with self._db.read() as conn:
            rows = conn.execute(_SELECT_FOR_ROOM, (room_id,)).fetchall()
        return [_run(row) for row in rows]

    def staged(self) -> list[Run]:
        """Runs neither applied nor discarded, oldest first."""
        with self._db.read() as conn:
            rows = conn.execute(_SELECT_STAGED).fetchall()
        return [_run(row) for row in rows]

    def applied(self, run_id: str, written: int, backed_up: int) -> bool:
        """Record that Apply finished. Returns whether a staged run was updated."""
        return self._finish(run_id, "applied", written, backed_up)

    def discarded(self, run_id: str) -> bool:
        """Record that the user discarded the run. Returns whether a staged run was updated."""
        return self._finish(run_id, "discarded", 0, 0)

    def _finish(self, run_id: str, status: str, written: int, backed_up: int) -> bool:
        stamp = self._clock().isoformat()
        with self._db.transaction() as conn:
            cursor = conn.execute(_FINISH_RUN, (status, stamp, written, backed_up, run_id))
        return cursor.rowcount == 1
