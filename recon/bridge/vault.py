"""The vault Recon owns, exposed to QML as `Vault` (task 2.1).

At launch, and whenever Settings points at another folder, `setUp` creates or
completes the vault on a worker (`engine.vault.bootstrap`). Obsidian refuses
`obsidian://` links to a vault it hasn't opened, so until Tyler says he's
opened this folder once ("Open folder as vault"), Home shows a one-time card
with the path, "Copy path" and "I've done that", and Recon shows no "Open in
Obsidian" buttons (`canOpenInObsidian`).
"""

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from recon.bridge.settings import SettingsBridge
from recon.bridge.workers import Submit
from recon.engine.vault import bootstrap
from recon.errors import ReconError
from recon.logging_setup import Safe

type Then = Callable[[], None]
type CopyText = Callable[[str], None]

_log = logging.getLogger(__name__)


class VaultBridge(QObject):
    """Sets the vault up and tracks whether Obsidian knows it."""

    changed = Signal()
    _done = Signal(object)

    def __init__(
        self,
        settings: SettingsBridge,
        copy_text: CopyText,
        *,
        submit: Submit,
        parent: QObject | None = None,
    ) -> None:
        """Wire the vault to settings.

        Args:
            settings: The vault folder, and the one Tyler opened in Obsidian.
            copy_text: Puts text on the clipboard ("Copy path").
            submit: Runs the bootstrap off the UI thread.
            parent: Qt parent.
        """
        super().__init__(parent)
        self._settings = settings
        self._copy_text = copy_text
        self._submit = submit
        self._ready = False
        self._problem = ""
        self._done.connect(self._finish)
        settings.vaultPathChanged.connect(self.setUp)
        settings.obsidianVaultChanged.connect(self.changed)

    def _path(self) -> str:
        return str(self._settings.property("vaultPath"))

    def _shown(self) -> str:
        return str(self._settings.property("vaultShown"))

    def _get_ready(self) -> bool:
        return self._ready

    def _get_problem(self) -> str:
        return self._problem

    def _obsidian_knows(self) -> bool:
        return bool(self._settings.property("obsidianVault") == self._path())

    def _needs_obsidian(self) -> bool:
        return self._ready and not self._obsidian_knows()

    path = Property(str, _path, notify=changed)
    shown = Property(str, _shown, notify=changed)
    ready = Property(bool, _get_ready, notify=changed)
    problem = Property(str, _get_problem, notify=changed)
    needsObsidian = Property(bool, _needs_obsidian, notify=changed)  # noqa: N815
    """Show the one-time "Open this folder in Obsidian once" step."""
    canOpenInObsidian = Property(bool, _obsidian_knows, notify=changed)  # noqa: N815
    """"Open in Obsidian" buttons may show (Phase 2.7 onwards)."""

    @Slot()
    def setUp(self) -> None:
        """Create or complete the vault's folders, Home and settings (off the UI thread)."""
        folder = Path(self._path())

        def job() -> None:
            # Thread boundary: report a problem, never crash the worker.
            try:
                bootstrap(folder)
            except ReconError as exc:
                message = exc.user_message
                self._done.emit(lambda: self._set(ready=False, problem=message))
                return
            except Exception as exc:  # thread boundary
                _log.error("vault setup failed: %s", Safe(type(exc).__name__))
                self._done.emit(lambda: self._set(ready=False, problem=ReconError.user_message))
                return
            self._done.emit(lambda: self._set(ready=True, problem=""))

        self._submit(job)

    @Slot()
    def copyPath(self) -> None:  # noqa: N802 - Qt naming, used from QML
        """Put the vault's path on the clipboard, for Obsidian's folder picker."""
        self._copy_text(self._path())

    @Slot()
    def confirmOpened(self) -> None:  # noqa: N802 - Qt naming, used from QML
        """Tyler opened this folder in Obsidian once: links to it work from now on."""
        self._settings.setProperty("obsidianVault", self._path())

    @Slot()
    def forgetOpened(self) -> None:  # noqa: N802 - Qt naming, used from QML
        """An obsidian:// link failed: show the one-time step again rather than an error."""
        self._settings.setProperty("obsidianVault", "")

    def _set(self, *, ready: bool, problem: str) -> None:
        self._ready, self._problem = ready, problem
        self.changed.emit()

    def _finish(self, then: Then) -> None:
        then()
