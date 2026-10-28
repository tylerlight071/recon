"""A room's run from staged notes to the vault, recorded in `app.db` (task 2.4).

Ties `engine.stage` (files) to the run and room records (database):
- `stage_room`: the rendered notes go to `runs/<run id>/staged/`; the run is
  recorded as staged and the room is in review.
- `apply_run`: Apply writes the vault (or raises, changing nothing); the run is
  recorded as applied, the room is done, and backups beyond the newest 20 go.
- `discard_run`: the staged notes go, the run is recorded as discarded, and the
  room is back to capturing, exactly as it was.
- `recover_runs`: at start-up, any Apply a crash interrupted is finished.

Task 2.5 runs these on the processing worker; nothing here touches Qt.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from recon.db.repositories import RoomRepository
from recon.db.runs import RunRepository
from recon.engine.notes import Rendered
from recon.engine.stage import (
    Applied,
    Manifest,
    apply,
    discard,
    load_manifest,
    prune_backups,
    recover,
    stage,
)
from recon.errors import ReconError
from recon.logging_setup import Safe
from recon.services.runs import RunLog, RunStore

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Processing:
    """Where runs, backups and the vault are, and the records to keep."""

    vault: Path
    runs: RunStore
    backups: Path
    rooms: RoomRepository
    records: RunRepository

    def folder(self, run_id: str) -> Path:
        """A run's folder."""
        return self.runs.root / run_id

    def stage_room(self, room_id: int, rendered: Rendered, run: RunLog) -> Manifest:
        """Stage a room's notes in `run`'s folder and put the room in review.

        Args:
            room_id: The room.
            rendered: Its notes (step 6).
            run: The run (from `RunStore.start`), whose folder holds the model logs too.

        Returns:
            The manifest, for the review screen.
        """
        manifest = stage(rendered, self.vault, run.folder, room_id=room_id)
        self.records.start(run.run_id, room_id)
        self.rooms.update_progress(room_id, status="in_review")
        _log.info(
            "run %s staged: %s to write, %s skipped",
            Safe(run.run_id),
            len(manifest.to_write),
            len(manifest.skipped),
        )
        return manifest

    def apply_run(self, run_id: str) -> Applied:
        """Apply a staged run, then record it and mark the room done.

        Raises:
            ApplyConflict: A note changed since staging; nothing was written.
            StagingDamagedError: The staged notes are missing or altered.
            UnsafePathError: A path would leave the vault.
        """
        manifest = load_manifest(self.folder(run_id))
        applied = apply(self.folder(run_id), self.vault, self.backups)
        self._finish_apply(run_id, manifest.room_id, applied)
        return applied

    def discard_run(self, run_id: str) -> None:
        """Throw the staged notes away and send the room back to capturing."""
        manifest = load_manifest(self.folder(run_id))
        discard(self.folder(run_id))
        self.records.discarded(run_id)
        self.rooms.update_progress(manifest.room_id, status="capturing")
        _log.info("run %s discarded", Safe(run_id))

    def discard_room(self, room_id: int) -> int:
        """Discard every staged run of a room ("Back to the room"); returns how many.

        The caller sets the room's status; this only removes staged notes.
        """
        count = 0
        for run in self.records.for_room(room_id):
            if run.status == "staged":
                discard(self.folder(run.id))
                self.records.discarded(run.id)
                count += 1
        return count

    def recover_runs(self) -> int:
        """Finish every Apply a crash interrupted; returns how many were finished."""
        finished = 0
        for run in self.records.staged():
            try:
                applied = recover(self.folder(run.id), self.vault)
            except ReconError as exc:
                _log.warning("run %s not recovered: %s", Safe(run.id), Safe(type(exc).__name__))
                continue
            if applied is not None:
                self._finish_apply(run.id, run.room_id, applied)
                finished += 1
        return finished

    def _finish_apply(self, run_id: str, room_id: int, applied: Applied) -> None:
        self.records.applied(run_id, applied.written, applied.backed_up)
        self.rooms.update_progress(room_id, status="done")
        pruned = prune_backups(self.backups)
        _log.info(
            "run %s applied: %s written, %s backed up, %s old backups pruned",
            Safe(run_id),
            applied.written,
            applied.backed_up,
            pruned,
        )
