"""How the screens hand over to each other, wired once for the app and its tests.

Home's "Start a room" opens Start; Start's new room, and Home's "Carry on",
open the panel. The main window goes back to Home without jumping in front,
so the panel and the browser stay where Tyler's eyes are.
"""

from recon.bridge.home import HomeBridge
from recon.bridge.navigation import NavigationBridge
from recon.bridge.start import StartRoomBridge


def connect_room_flow(
    navigation: NavigationBridge, home: HomeBridge, start: StartRoomBridge
) -> None:
    """Connect Home and Start to navigation (task 1.9 loads the room into the panel)."""
    home.startRequested.connect(lambda: navigation.open("start"))
    home.resumeRequested.connect(lambda _room_id: navigation.showPanel())

    def on_started(_room_id: int) -> None:
        navigation.switch_to("home")
        navigation.showPanel()

    start.started.connect(on_started)
