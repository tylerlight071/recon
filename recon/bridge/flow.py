"""How the screens hand over to each other, wired once for the app and its tests.

Home's "Start a room" opens Start. A new room, and Home's "Carry on", load the
room into the panel and show it. The main window goes back to Home without
jumping in front, so the panel and the browser stay where Tyler's eyes are,
and Home keeps "Where was I?" current as he moves through tasks.
"""

from recon.bridge.home import HomeBridge
from recon.bridge.navigation import NavigationBridge
from recon.bridge.session import RoomSessionBridge
from recon.bridge.start import StartRoomBridge


def connect_room_flow(
    navigation: NavigationBridge,
    home: HomeBridge,
    start: StartRoomBridge,
    session: RoomSessionBridge,
) -> None:
    """Connect Home, Start and the room session to navigation."""
    home.startRequested.connect(lambda: navigation.open("start"))

    def open_room(room_id: int) -> None:
        session.open(room_id)
        navigation.showPanel()

    def on_started(room_id: int) -> None:
        navigation.switch_to("home")
        open_room(room_id)

    home.resumeRequested.connect(open_room)
    start.started.connect(on_started)
    session.changed.connect(home.refresh)
