"""Which screen the main window shows, exposed to QML as the `Navigation` singleton."""

from typing import Final

from PySide6.QtCore import Property, QObject, Signal, Slot

MAIN_SCREENS: Final = ("home", "settings")
"""Main-window screens that exist so far. Later tasks add review, cards, revise, ask, library."""


class NavigationBridge(QObject):
    """Opens main-window screens and the panel; the windows react to its signals."""

    currentScreenChanged = Signal()  # noqa: N815 - Qt naming, used from QML
    mainWindowRequested = Signal()  # noqa: N815 - Qt naming, used from QML
    panelRequested = Signal()  # noqa: N815 - Qt naming, used from QML

    def __init__(self, parent: QObject | None = None) -> None:
        """Start on Home."""
        super().__init__(parent)
        self._screen = MAIN_SCREENS[0]

    def _get_screen(self) -> str:
        return self._screen

    currentScreen = Property(str, _get_screen, notify=currentScreenChanged)  # noqa: N815

    @Slot(str)
    def open(self, screen: str) -> None:
        """Show `screen` in the main window and bring that window forward.

        Unknown screen names are ignored, so a stray call can't blank the window.
        """
        if screen not in MAIN_SCREENS:
            return
        if screen != self._screen:
            self._screen = screen
            self.currentScreenChanged.emit()
        self.mainWindowRequested.emit()

    @Slot()
    def showPanel(self) -> None:  # noqa: N802 - Qt naming, used from QML
        """Show the side panel (a room session starts there)."""
        self.panelRequested.emit()
