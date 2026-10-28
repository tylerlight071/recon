"""Which screen the main window shows, exposed to QML as the `Navigation` singleton."""

from typing import Final

from PySide6.QtCore import Property, QObject, Signal, Slot

MAIN_SCREENS: Final = ("home", "start", "review", "done", "library", "settings")
"""Main-window screens that exist so far. Later tasks add cards, revise and ask.

"start" (Start a room), "review" and "done" have no sidebar entries of their own:
they're reached from Home, the panel or a notification.
"""


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
        if self.switch_to(screen):
            self.mainWindowRequested.emit()

    def switch_to(self, screen: str) -> bool:
        """Change the main window's screen without bringing the window forward.

        Returns:
            False if `screen` isn't a known screen (nothing changes).
        """
        if screen not in MAIN_SCREENS:
            return False
        if screen != self._screen:
            self._screen = screen
            self.currentScreenChanged.emit()
        return True

    @Slot()
    def showPanel(self) -> None:  # noqa: N802 - Qt naming, used from QML
        """Show the side panel (a room session starts there)."""
        self.panelRequested.emit()
