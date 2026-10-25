"""Settings exposed to QML as the `AppSettings` singleton."""

from collections.abc import Callable

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from recon.config import PINNING_CHOICES, Settings, clamp_panel_width

SAVE_DELAY_MS = 500
"""Saves wait for changes to settle, e.g. while the panel is being dragged wider."""


class SettingsBridge(QObject):
    """Holds the current settings and saves them shortly after they change.

    The bridge only clamps and schedules; validation and the file format live
    in `recon.config`.
    """

    panelWidthChanged = Signal()  # noqa: N815 - Qt naming, used from QML
    pinningChanged = Signal()  # noqa: N815 - Qt naming, used from QML
    chimeChanged = Signal()  # noqa: N815 - Qt naming, used from QML

    def __init__(
        self,
        settings: Settings,
        save: Callable[[Settings], None],
        parent: QObject | None = None,
    ) -> None:
        """Wrap `settings`; `save` is called with the new settings after changes.

        Args:
            settings: Settings loaded at start-up.
            save: Persists settings (injected so tests can fake it).
            parent: Qt parent.
        """
        super().__init__(parent)
        self._settings = settings
        self._save = save
        self._dirty = False
        self._timer = QTimer(self, singleShot=True, interval=SAVE_DELAY_MS)
        self._timer.timeout.connect(self.flush)

    @property
    def settings(self) -> Settings:
        """The current settings."""
        return self._settings

    def _get_panel_width(self) -> int:
        return self._settings.panel_width

    def _set_panel_width(self, width: float) -> None:
        clamped = clamp_panel_width(width)
        if clamped == self._settings.panel_width:
            return
        self._update(panel_width=clamped)
        self.panelWidthChanged.emit()

    panelWidth = Property(  # noqa: N815 - Qt naming, used from QML
        int, _get_panel_width, _set_panel_width, notify=panelWidthChanged
    )

    def _get_pinning(self) -> str:
        return self._settings.kwin_pinning

    def _set_pinning(self, choice: str) -> None:
        if choice not in PINNING_CHOICES or choice == self._settings.kwin_pinning:
            return
        self._update(kwin_pinning=choice)
        self.pinningChanged.emit()

    pinning = Property(str, _get_pinning, _set_pinning, notify=pinningChanged)
    """"ask", "on" or "off"; anything else is ignored."""

    def _get_chime(self) -> bool:
        return self._settings.chime

    def _set_chime(self, on: bool) -> None:
        if on == self._settings.chime:
            return
        self._update(chime=on)
        self.chimeChanged.emit()

    chime = Property(bool, _get_chime, _set_chime, notify=chimeChanged)
    """Play the focus chime (Settings, task 1.14)."""

    def _update(self, **changes: object) -> None:
        self._settings = self._settings.model_copy(update=changes)
        self._dirty = True
        self._timer.start()

    @Slot()
    def flush(self) -> None:
        """Save now if anything changed (also called when the app quits)."""
        self._timer.stop()
        if self._dirty:
            self._save(self._settings)
            self._dirty = False
