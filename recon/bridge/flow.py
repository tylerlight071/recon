"""How the screens hand over to each other, wired once for the app and its tests.

Home's "Start a room" opens Start. A new room, and Home's "Carry on", load the
room into the panel and show it. The main window goes back to Home without
jumping in front, so the panel and the browser stay where the user's eyes are,
and Home keeps "Where was I?" current as the user moves through tasks.
"""

from recon.bridge.finish import FinishBridge
from recon.bridge.focus import FocusBridge
from recon.bridge.home import HomeBridge
from recon.bridge.navigation import NavigationBridge
from recon.bridge.processing import ProcessingBridge
from recon.bridge.session import RoomSessionBridge
from recon.bridge.start import StartRoomBridge


def connect_room_flow(
    navigation: NavigationBridge,
    home: HomeBridge,
    start: StartRoomBridge,
    session: RoomSessionBridge,
    focus: FocusBridge,
) -> None:
    """Connect Home, Start, the room session and its timer to navigation."""
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
    session.taskShown.connect(lambda: focus.set_task(session.current_task()))
    session.activity.connect(focus.activity)


def connect_finish(
    navigation: NavigationBridge,
    home: HomeBridge,
    session: RoomSessionBridge,
    focus: FocusBridge,
    finish: FinishBridge,
) -> None:
    """Finish room hands over to Finish; "Back to the room" and "Done" hand back."""

    def finish_room(room_id: int) -> None:
        focus.set_task(None)  # saves the last seconds first (same worker, so in order)
        session.closeRoom()
        finish.open(room_id)

    def reopen(room_id: int) -> None:
        session.open(room_id)
        navigation.showPanel()

    def revisit(room_id: int) -> None:
        finish.revisit(room_id)
        navigation.showPanel()

    session.finishRequested.connect(finish_room)
    home.finishedRequested.connect(revisit)
    finish.reopenRequested.connect(reopen)
    finish.closed.connect(home.refresh)
    finish.closed.connect(lambda: navigation.open("home"))


def connect_processing(
    navigation: NavigationBridge,
    home: HomeBridge,
    finish: FinishBridge,
    processing: ProcessingBridge,
) -> None:
    """A finished room is processed; the panel follows the room it shows.

    A notification's click opens that room's Finish screen (the review screen
    takes over in task 2.7). "Back to the room" takes it out of processing.
    """

    def process(room_id: int) -> None:
        processing.show(room_id)
        processing.enqueue(room_id)

    def reopen(room_id: int) -> None:
        processing.withdraw(room_id)
        processing.show(0)

    def open_room(room_id: int) -> None:
        processing.show(room_id)
        finish.revisit(room_id)
        navigation.showPanel()

    finish.processRequested.connect(process)
    finish.reopenRequested.connect(reopen)
    finish.closed.connect(lambda: processing.show(0))
    home.finishedRequested.connect(processing.show)
    processing.readyForReview.connect(lambda _room: home.refresh())
    processing.reviewRequested.connect(open_room)
