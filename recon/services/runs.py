"""Run folders: the raw model responses for one processing run (`runs/<run_id>/`).

Raw responses are content, so they never go to `app.log` (CLAUDE.md, Logging).
They go here instead, privately (folders 0700, files 0600), for debugging a run,
and are deleted after 30 days.
"""

import json
import logging
import shutil
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from recon.fs import atomic_write_text
from recon.paths import ensure_private_dir

KEEP_DAYS: Final = 30
_STAMP: Final = "%Y%m%dT%H%M%S"

type Clock = Callable[[], datetime]
type NewId = Callable[[], str]

_log = logging.getLogger(__name__)


class RunLog:
    """One run's folder: each model call's raw response, as JSON."""

    def __init__(self, folder: Path) -> None:
        """Use `folder` (created privately on first write)."""
        self.folder = folder

    @property
    def run_id(self) -> str:
        """The run's ID (its folder name)."""
        return self.folder.name

    def record(self, step: str, attempt: int, payload: dict[str, object]) -> Path:
        """Write one call's raw response; returns the file.

        Args:
            step: The pipeline step, e.g. "extract" (letters, digits, - and _ only).
            attempt: 1 for the first call, 2 for the retry.
            payload: What to keep: model, prompt size, raw text, timings.
        """
        if not step.replace("-", "").replace("_", "").isalnum():
            msg = "step names are letters, digits, - and _"
            raise ValueError(msg)
        ensure_private_dir(self.folder)
        path = self.folder / f"{step}-{attempt}.json"
        atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return path


class RunStore:
    """Creates run folders under `runs/` and deletes ones older than 30 days."""

    def __init__(self, root: Path, clock: Clock, new_id: NewId) -> None:
        """Keep runs in `root`; `clock` and `new_id` are injected for tests."""
        self.root = root
        self._clock = clock
        self._new_id = new_id

    def start(self) -> RunLog:
        """A new run: its ID starts with the time, so folders sort by age."""
        run_id = f"{self._clock().strftime(_STAMP)}-{self._new_id()}"
        return RunLog(self.root / run_id)

    def prune(self, keep_days: int = KEEP_DAYS) -> int:
        """Delete runs older than `keep_days`; returns how many went."""
        if not self.root.is_dir():
            return 0
        cutoff = self._clock() - timedelta(days=keep_days)
        removed = 0
        for folder in self.root.iterdir():
            started = _started(folder.name)
            if folder.is_dir() and not folder.is_symlink() and started and started < cutoff:
                shutil.rmtree(folder)
                removed += 1
        if removed:
            _log.info("deleted %s old run folder(s)", removed)
        return removed


def _started(run_id: str) -> datetime | None:
    try:
        # IDs are stamped in UTC (the clock is utc_now), so read them back as UTC.
        return datetime.strptime(run_id.split("-", 1)[0], _STAMP).replace(tzinfo=UTC)
    except ValueError:
        return None
