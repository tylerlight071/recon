"""Save block edits within half a second, off the UI thread (hard rule 7).

Each keystroke calls `put(block_id, content)`. Edits to the same block
coalesce, and a block is written at most `delay_s` after its *first* unsaved
change. That's a max-latency debounce: continuous typing can't postpone the
save forever, so a crash loses at most about half a second. `flush()` writes
everything now (task switch, window close); `close()` flushes and stops.

A failed write keeps the edit queued and retries, so nothing is dropped.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from recon.db.models import BlockContent
from recon.logging_setup import Safe

DELAY_S: Final = 0.5
RETRY_S: Final = 1.0

type Save = Callable[[int, BlockContent], object]
type Clock = Callable[[], float]

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class _Pending:
    content: BlockContent
    due: float


class AutosaveQueue:
    """A writer thread that saves the latest content of each edited block."""

    def __init__(
        self,
        save: Save,
        delay_s: float = DELAY_S,
        clock: Clock = time.monotonic,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Start the writer thread.

        Args:
            save: Writes one block's content (normally `BlockRepository.update_content`).
            delay_s: Longest an edit waits before being written.
            clock: Monotonic seconds (tests may pass their own).
            on_error: Told about a failed write (e.g. to show "Couldn't save").
        """
        self._save = save
        self._delay = delay_s
        self._clock = clock
        self._on_error = on_error
        self._pending: dict[int, _Pending] = {}
        self._cond = threading.Condition()
        self._stopping = False
        self._writing = 0
        self._thread = threading.Thread(target=self._run, name="recon-autosave", daemon=True)
        self._thread.start()

    def put(self, block_id: int, content: BlockContent) -> None:
        """Queue the latest content for a block (cheap; call on every keystroke)."""
        with self._cond:
            existing = self._pending.get(block_id)
            due = existing.due if existing else self._clock() + self._delay
            self._pending[block_id] = _Pending(content, due)
            self._cond.notify()

    @property
    def pending(self) -> int:
        """How many blocks have unsaved edits."""
        with self._cond:
            return len(self._pending)

    def flush(self, timeout_s: float = 5.0) -> bool:
        """Write every queued edit now and wait until they're saved.

        Returns:
            True when nothing is left unsaved within the timeout.
        """
        deadline = self._clock() + timeout_s
        with self._cond:
            for item in self._pending.values():
                item.due = 0.0
            self._cond.notify()
            while (self._pending or self._writing) and self._clock() < deadline:
                self._cond.wait(timeout=0.05)
            return not self._pending and not self._writing

    def close(self) -> bool:
        """Flush, then stop the writer thread. Returns whether everything was saved."""
        saved = self.flush()
        with self._cond:
            self._stopping = True
            self._cond.notify()
        self._thread.join(timeout=5.0)
        return saved

    def _run(self) -> None:
        while True:
            with self._cond:
                batch = self._wait_for_due()
                if batch is None:
                    return
                self._writing += 1
            try:
                self._write(batch)
            finally:
                with self._cond:
                    self._writing -= 1
                    self._cond.notify_all()

    def _wait_for_due(self) -> dict[int, BlockContent] | None:
        # Called with the lock held. None means: stop.
        while True:
            if self._stopping and not self._pending:
                return None
            now = self._clock()
            due = {k: v.content for k, v in self._pending.items() if v.due <= now}
            if due:
                for block_id in due:
                    del self._pending[block_id]
                return due
            soonest = min((v.due for v in self._pending.values()), default=None)
            self._cond.wait(timeout=None if soonest is None else max(0.0, soonest - now))

    def _write(self, batch: dict[int, BlockContent]) -> None:
        for block_id, content in batch.items():
            try:
                self._save(block_id, content)
            # Thread boundary (CLAUDE.md, Errors): catch everything, log, retry, report.
            except Exception as exc:
                _log.warning("autosave of block %s failed: %s", block_id, Safe(type(exc).__name__))
                self._requeue(block_id, content)
                if self._on_error is not None:
                    self._on_error(exc)

    def _requeue(self, block_id: int, content: BlockContent) -> None:
        with self._cond:
            # A newer edit that arrived meanwhile wins; otherwise retry this one.
            if block_id not in self._pending:
                self._pending[block_id] = _Pending(content, self._clock() + RETRY_S)
