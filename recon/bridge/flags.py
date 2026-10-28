"""The flag filter exposed to QML as `FlagGuard` (hard rule 2, task 1.6).

Block editors pass each edit through `clean()`, so a flag disappears from the
screen as well as from storage, and the panel shows a calm "Flag skipped"
notice. A lone hex string (an example hash) can be kept with "Not a flag,
keep it"; braced flags never can. Flag text is never logged: only counts.
"""

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal, Slot

from recon.bridge.workers import Submit, thread_pool_submit
from recon.engine.flags_filter import strip_flags
from recon.logging_setup import Safe

type Keep = Callable[[int, str], bool]

_log = logging.getLogger(__name__)


class FlagGuard(QObject):
    """Cleans editor text and handles "Not a flag, keep it"."""

    flagSkipped = Signal(int, str)  # noqa: N815 - Qt naming, used from QML
    """(block id, keepable): `keepable` is the one hex string the user may keep, else ""."""
    keptRestored = Signal(int, str)  # noqa: N815 - Qt naming, used from QML
    """(block id, text): put the kept string back in that block's editor."""
    _kept = Signal(int, str, bool)
    fieldFlagSkipped = Signal(str)  # noqa: N815 - Qt naming, used from QML
    """A flag left a title or room detail; the argument names the window ("panel", "main")."""

    def __init__(
        self, keep: Keep, submit: Submit = thread_pool_submit, parent: QObject | None = None
    ) -> None:
        """Wire the guard.

        Args:
            keep: Records a kept hex string (normally `BlockRepository.keep_lookalike`).
            submit: Runs that write off the UI thread (the room worker, so it lands
                in order with the block's other saves).
            parent: Qt parent.
        """
        super().__init__(parent)
        self._keep = keep
        self._submit = submit
        # Emitted from the worker; a bound slot, so Qt delivers it on the UI thread.
        self._kept.connect(self._on_kept)

    @Slot(int, str, list, result=str)
    def clean(self, block_id: int, text: str, kept: list[str]) -> str:
        """The text with flags removed; tells the panel if anything was skipped.

        Args:
            block_id: The block being edited.
            text: What's in the editor now.
            kept: Hex strings already kept for this block.

        Returns:
            The text to show and save.
        """
        result = strip_flags(text, kept)
        if result.changed:
            only = result.removed[0] if len(result.removed) == 1 else None
            keepable = only.text if only is not None and only.keepable else ""
            _log.info("skipped %s flag-shaped string(s) in block %s", len(result.removed), block_id)
            self.flagSkipped.emit(block_id, keepable)
        return result.text

    @Slot(str, str, result=str)
    def cleanField(self, text: str, window: str) -> str:  # noqa: N802 - Qt naming, used from QML
        """A task title or room detail with flags removed (audit F-14).

        These are names, not notes, so nothing here can be kept.

        Args:
            text: What's in the field now.
            window: Which window shows the notice ("panel" or "main").

        Returns:
            The text to show and save.
        """
        result = strip_flags(text)
        if result.changed:
            _log.info("skipped %s flag-shaped string(s) in a field", len(result.removed))
            self.fieldFlagSkipped.emit(window)
        return result.text

    @Slot(int, str)
    def keep(self, block_id: int, text: str) -> None:
        """The user said "Not a flag, keep it": remember it, then restore it in the editor."""

        def job() -> None:
            try:
                ok = self._keep(block_id, text)
            except Exception as exc:  # thread boundary: log the type, never the text
                _log.warning("keep failed: %s", Safe(type(exc).__name__))
                ok = False
            self._kept.emit(block_id, text, ok)

        self._submit(job)

    def _on_kept(self, block_id: int, text: str, ok: bool) -> None:
        if ok:
            self.keptRestored.emit(block_id, text)
