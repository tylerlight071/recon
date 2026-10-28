"""Panel pinning exposed to QML as the `Pinning` object (task 1.4)."""

from collections.abc import Callable
from typing import Protocol

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from recon.bridge.settings import SettingsBridge
from recon.bridge.workers import Submit, thread_pool_submit
from recon.services.kwin import Method, PanelGeometry

REAPPLY_DELAY_MS = 500
"""A width change while pinned rewrites the rule once the change settles."""

type ScreenArea = Callable[[], tuple[int, int, int, int]]


class Pinner(Protocol):
    """What the bridge needs from `recon.services.kwin.KWinPinning`."""

    def pin(self, geometry: PanelGeometry) -> Method | None:
        """Pin the panel; return how, or None."""

    def unpin(self) -> bool:
        """Remove the pin; return whether it's gone."""


class PinningBridge(QObject):
    """Asks once, pins or unpins off the UI thread, and reports failures.

    The KDE commands run on a worker thread (the UI thread never blocks); the
    result comes back through a signal, which Qt delivers on the UI thread.
    """

    askNeededChanged = Signal()  # noqa: N815 - Qt naming, used from QML
    pinFailed = Signal()  # noqa: N815 - Qt naming, used from QML
    unpinFailed = Signal()  # noqa: N815 - Qt naming, used from QML
    _finished = Signal(object)
    # Re-emitted from the worker thread; Qt queues it back to the UI thread.
    _unpin_failed = Signal()

    def __init__(
        self,
        settings: SettingsBridge,
        pinner: Pinner,
        screen_area: ScreenArea,
        submit: Submit = thread_pool_submit,
        parent: QObject | None = None,
    ) -> None:
        """Wire the bridge to settings and the pinning service.

        Args:
            settings: Holds the choice ("ask", "on", "off") and the panel width.
            pinner: Adds and removes the KWin rule.
            screen_area: The primary screen's area (x, y, w, h); KWin fits the height.
            submit: Runs a job off the UI thread (tests pass a synchronous one).
            parent: Qt parent.
        """
        super().__init__(parent)
        self._settings = settings
        self._pinner = pinner
        self._screen_area = screen_area
        self._submit = submit
        self.last_method: Method | None = None
        """How the most recent pin worked (rule or script), for logs and tests."""
        self._reapply = QTimer(self, singleShot=True, interval=REAPPLY_DELAY_MS)
        self._reapply.timeout.connect(self.applyIfOn)
        self._finished.connect(self._on_finished)
        self._unpin_failed.connect(self.unpinFailed)
        settings.pinningChanged.connect(self.askNeededChanged)
        settings.panelWidthChanged.connect(self._on_width_changed)

    def _get_ask_needed(self) -> bool:
        return bool(self._settings.property("pinning") == "ask")

    askNeeded = Property(bool, _get_ask_needed, notify=askNeededChanged)  # noqa: N815

    @Slot()
    def pin(self) -> None:
        """The user said yes: remember it and pin now."""
        self._settings.setProperty("pinning", "on")
        self.applyIfOn()

    @Slot()
    def decline(self) -> None:
        """The user said not now: don't ask again (Settings can turn it on)."""
        self._settings.setProperty("pinning", "off")

    @Slot()
    def unpin(self) -> None:
        """Turn pinning off and remove Recon's rule (Settings, task 1.14)."""
        self._settings.setProperty("pinning", "off")

        def job() -> None:
            # Pinned again before this ran? Then the rule stays (audit F-16).
            if self._settings.settings.kwin_pinning == "on":
                return
            if not self._pinner.unpin():
                self._unpin_failed.emit()

        self._submit(job)

    @Slot()
    def applyIfOn(self) -> None:  # noqa: N802 - Qt naming, used from QML and at start-up
        """(Re)write the pin with the current width, if pinning is on."""
        if self._settings.property("pinning") != "on":
            return
        geometry = PanelGeometry.right_edge(
            self._screen_area(), int(self._settings.property("panelWidth"))
        )

        def job() -> None:
            # Unpinned before this ran? Then don't write the rule (audit F-16).
            if self._settings.settings.kwin_pinning != "on":
                return
            self._finished.emit(self._pinner.pin(geometry))

        self._submit(job)

    def _on_width_changed(self) -> None:
        if self._settings.property("pinning") == "on":
            self._reapply.start()

    def _on_finished(self, method: Method | None) -> None:
        self.last_method = method
        if method is None:
            self.pinFailed.emit()
