"""Whether Ollama and Recon's models are ready, exposed to QML as `Models` (task 2.2).

Checked once at launch and whenever Settings opens or Tyler presses "Check
again", on a worker (a check waits a few seconds at most). Settings shows one
plain line about it and, for a model that isn't installed yet, the exact
`ollama pull` command to run. Recon never pulls models itself: each new
download is Tyler's to start (CLAUDE.md, hard rule 1).
"""

import logging
from collections.abc import Callable

from PySide6.QtCore import Property, QObject, Signal, Slot

from recon.bridge.settings import SettingsBridge
from recon.bridge.workers import Submit
from recon.errors import ReconError
from recon.logging_setup import Safe
from recon.services.ollama import OllamaService, Status

type ServiceFor = Callable[[str], OllamaService]
"""Builds the service for an Ollama address (raises UnsafeHostError for another machine)."""
type CopyText = Callable[[str], None]

_log = logging.getLogger(__name__)

CHECKING = "checking"
READY = "ready"
OFFLINE = "offline"
MISSING = "missing"
PROBLEM = "problem"

_OFFLINE_TEXT = "Couldn't reach Ollama. Is it running? Start it, then press Check again."
_READY_TEXT = "Ollama is running and has every model Recon uses."


class ModelsBridge(QObject):
    """Ollama's status for Settings: running, which models are missing, what to do."""

    changed = Signal()
    _done = Signal(object, str)

    def __init__(
        self,
        settings: SettingsBridge,
        service_for: ServiceFor,
        copy_text: CopyText,
        *,
        submit: Submit,
        parent: QObject | None = None,
    ) -> None:
        """Wire the check.

        Args:
            settings: The model names and Ollama's address.
            service_for: Builds the Ollama service (a fake in tests).
            copy_text: Puts the `ollama pull` commands on the clipboard.
            submit: Runs the check off the UI thread.
            parent: Qt parent.
        """
        super().__init__(parent)
        self._settings = settings
        self._service_for = service_for
        self._copy_text = copy_text
        self._submit = submit
        self._state = CHECKING
        self._message = "Checking Ollama…"
        self._missing: tuple[str, ...] = ()
        self._checking = False
        self._done.connect(self._finish)

    # ---- Properties --------------------------------------------------------------------

    def _get_state(self) -> str:
        return self._state

    def _get_message(self) -> str:
        return self._message

    def _get_checking(self) -> bool:
        return self._checking

    def _get_commands(self) -> str:
        return "\n".join(f"ollama pull {name}" for name in self._missing)

    def _get_roles(self) -> list[dict[str, str]]:
        current = self._settings.settings
        return [
            {"role": "Notes and questions", "name": current.text_model},
            {"role": "Screenshots", "name": current.vision_model},
            {"role": "Matching notes", "name": current.embedding_model},
        ]

    state = Property(str, _get_state, notify=changed)
    """One of "checking", "ready", "offline", "missing" or "problem"."""
    message = Property(str, _get_message, notify=changed)
    checking = Property(bool, _get_checking, notify=changed)
    commands = Property(str, _get_commands, notify=changed)
    """The `ollama pull` lines for missing models, one per line ("" when none)."""
    roles = Property(list, _get_roles, notify=changed)
    """What each model is for, and its name, for Settings."""

    # ---- Slots -------------------------------------------------------------------------

    @Slot()
    def check(self) -> None:
        """Ask Ollama what it has (ignored while a check is already running)."""
        if self._checking:
            return
        self._checking = True
        if self._state != READY:
            self._state, self._message = CHECKING, "Checking Ollama…"
        self.changed.emit()
        current = self._settings.settings
        host, models = current.ollama_host, current.models

        def job() -> None:
            # Thread boundary: whatever happens, Settings gets a calm line, never a crash.
            try:
                status = self._service_for(host).status(models)
            except ReconError as exc:
                self._done.emit(None, exc.user_message)
                return
            except Exception as exc:  # thread boundary
                _log.error("ollama check failed: %s", Safe(type(exc).__name__))
                self._done.emit(None, ReconError.user_message)
                return
            self._done.emit(status, "")

        self._submit(job)

    @Slot()
    def copyCommands(self) -> None:  # noqa: N802 - Qt naming, used from QML
        """Put the `ollama pull` commands on the clipboard."""
        if self._missing:
            self._copy_text(self._get_commands())

    # ---- Results -----------------------------------------------------------------------

    def _finish(self, status: Status | None, problem: str) -> None:
        self._checking = False
        self._missing = ()
        if status is None:
            self._state, self._message = PROBLEM, problem
        elif not status.running:
            self._state, self._message = OFFLINE, _OFFLINE_TEXT
        elif status.missing:
            self._missing = status.missing
            self._state, self._message = MISSING, _missing_text(status.missing)
        else:
            self._state, self._message = READY, _READY_TEXT
        _log.info("ollama check: %s (%s missing)", Safe(self._state), len(self._missing))
        self.changed.emit()


def _missing_text(missing: tuple[str, ...]) -> str:
    if len(missing) == 1:
        return (
            f"Ollama is running, but {missing[0]} isn't installed yet. "
            "Run this in a terminal, then press Check again:"
        )
    return (
        f"Ollama is running, but {len(missing)} models aren't installed yet. "
        "Run these in a terminal, then press Check again:"
    )
