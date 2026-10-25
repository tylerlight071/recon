"""Settings exposed to QML as the `AppSettings` singleton."""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, SignalInstance, Slot

from recon.config import ACCENTS, PINNING_CHOICES, Settings, clamp_panel_width, vault_folder

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
    exportFolderChanged = Signal()  # noqa: N815 - Qt naming, used from QML
    accentChanged = Signal()  # noqa: N815 - Qt naming, used from QML
    reduceMotionChanged = Signal()  # noqa: N815 - Qt naming, used from QML
    vaultPathChanged = Signal()  # noqa: N815 - Qt naming, used from QML

    def __init__(
        self,
        settings: Settings,
        save: Callable[[Settings], None],
        parent: QObject | None = None,
        home: Path | None = None,
    ) -> None:
        """Wrap `settings`; `save` is called with the new settings after changes.

        Args:
            settings: Settings loaded at start-up.
            save: Persists settings (injected so tests can fake it).
            parent: Qt parent.
            home: Tyler's home folder, for ~/ paths (defaults to Path.home()).
        """
        super().__init__(parent)
        self._settings = settings
        self._save = save
        self._home = home or Path.home()
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
        self._change("chime", on, self.chimeChanged)

    chime = Property(bool, _get_chime, _set_chime, notify=chimeChanged)
    """Play the focus chime."""

    def _get_export_folder(self) -> str:
        return self._settings.export_folder

    def _set_export_folder(self, folder: str) -> None:
        self._change("export_folder", folder, self.exportFolderChanged)

    exportFolder = Property(  # noqa: N815 - Qt naming, used from QML
        str, _get_export_folder, _set_export_folder, notify=exportFolderChanged
    )
    """The folder the last Markdown export went to (task 1.13)."""

    def _get_accent(self) -> str:
        return self._settings.accent

    def _set_accent(self, accent: str) -> None:
        if accent in ACCENTS:
            self._change("accent", accent, self.accentChanged)

    def _get_accents(self) -> list[str]:
        return list(ACCENTS)

    accent = Property(str, _get_accent, _set_accent, notify=accentChanged)
    accents = Property(list, _get_accents, constant=True)
    """The accent choices, in order."""
    """"violet", "cyan" or "green"; anything else is ignored."""

    def _get_reduce_motion(self) -> bool:
        return self._settings.reduce_motion

    def _set_reduce_motion(self, on: bool) -> None:
        self._change("reduce_motion", on, self.reduceMotionChanged)

    reduceMotion = Property(  # noqa: N815 - Qt naming, used from QML
        bool, _get_reduce_motion, _set_reduce_motion, notify=reduceMotionChanged
    )

    def _get_vault_path(self) -> str:
        return str(vault_folder(self._settings, self._home))

    def _get_vault_shown(self) -> str:
        folder = vault_folder(self._settings, self._home)
        return (
            f"~/{folder.relative_to(self._home)}"
            if folder.is_relative_to(self._home)
            else str(folder)
        )

    def _get_vault_url(self) -> str:
        return QUrl.fromLocalFile(self._get_vault_path()).toString()

    vaultPath = Property(str, _get_vault_path, notify=vaultPathChanged)  # noqa: N815
    vaultUrl = Property(str, _get_vault_url, notify=vaultPathChanged)  # noqa: N815
    vaultShown = Property(str, _get_vault_shown, notify=vaultPathChanged)  # noqa: N815
    """The vault folder as Tyler would say it (~/Cyber Vault)."""

    @Slot(str)
    def chooseVault(self, folder_url: str) -> None:  # noqa: N802 - Qt naming, used from QML
        """Use the folder picked in Settings (a local file URL) as the vault."""
        folder = QUrl(folder_url).toLocalFile()
        if folder:
            self._change("vault_path", folder, self.vaultPathChanged)

    def _change(self, field: str, value: object, changed: SignalInstance) -> None:
        if getattr(self._settings, field) == value:
            return
        self._update(**{field: value})
        changed.emit()

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
