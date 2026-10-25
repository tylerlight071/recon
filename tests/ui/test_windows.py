"""Task 1.3: the panel and main window share one engine and behave as the spec says."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QMetaObject, QObject, QPoint, QPointF, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from recon.app import QmlEngine, create_engine, load_windows, root_window
from recon.bridge.editors import EditorsBridge
from recon.bridge.flags import FlagGuard
from recon.bridge.flow import connect_room_flow
from recon.bridge.home import HomeBridge
from recon.bridge.navigation import NavigationBridge
from recon.bridge.pinning import PinningBridge
from recon.bridge.session import RoomSessionBridge
from recon.bridge.settings import SettingsBridge
from recon.bridge.start import StartRoomBridge
from recon.config import Settings
from recon.db.connection import Database
from recon.db.migrate import migrate
from recon.db.models import NewRoom
from recon.db.repositories import (
    BlockRepository,
    RoomRepository,
    TaskRepository,
    UndoRepository,
    utc_now,
)
from tests.bridge.fakes import FakeAutosave
from tests.bridge.test_pinning_bridge import FakePinner
from tests.ui.qml_harness import app, wait, wait_until


@dataclass(frozen=True)
class WithRooms:
    """Fixture parameter: settings plus rooms to create before the windows load."""

    settings: Settings
    rooms: tuple[NewRoom, ...] = ()


@dataclass
class Running:
    qml: QmlEngine
    settings: SettingsBridge
    navigation: NavigationBridge
    main: QQuickWindow
    panel: QQuickWindow
    warnings: list[str]
    saved: list[Settings]
    pinner: "FakePinner"
    flag_guard: FlagGuard
    kept: list[tuple[int, str]]
    rooms: RoomRepository
    session: RoomSessionBridge
    autosave: FakeAutosave
    blocks: BlockRepository
    tasks: TaskRepository

    def find(self, window: QQuickWindow, name: str) -> QObject:
        # Walk the visual tree: Repeater delegates aren't QObject children of the window.
        pending: list[QQuickItem] = [window.contentItem()]
        while pending:
            item = pending.pop()
            if item.objectName() == name:
                return item
            pending.extend(item.childItems())
        raise AssertionError(name)

    def find_object(self, window: QQuickWindow, name: str) -> QObject:
        # Popups (Dialog) live outside the item tree, so search QObject children.
        found = window.findChild(QObject, name)
        assert found is not None, name
        return found


@pytest.fixture
def running(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Running]:
    app()
    (tmp_path / "recon").mkdir(mode=0o700)
    db = Database.open(tmp_path / "recon" / "app.db")
    migrate(db)
    # Most tests don't want the first-launch pin question in the way.
    param = getattr(request, "param", Settings(kwin_pinning="off"))
    initial = param.settings if isinstance(param, WithRooms) else param
    rooms = RoomRepository(db)
    for room in param.rooms if isinstance(param, WithRooms) else ():
        rooms.create(room)
    owner = QObject()
    saved: list[Settings] = []
    settings = SettingsBridge(initial, saved.append, parent=owner)
    navigation = NavigationBridge(parent=owner)
    pinner = FakePinner()
    pinning = PinningBridge(
        settings, pinner, lambda: (0, 0, 1280, 720), lambda job: job(), parent=owner
    )
    kept: list[tuple[int, str]] = []
    flag_guard = FlagGuard(lambda block, text: kept.append((block, text)) is None, parent=owner)
    blocks = BlockRepository(db)
    home = HomeBridge(rooms, blocks, utc_now, parent=owner)
    start = StartRoomBridge(rooms, lambda job: job(), parent=owner)
    autosave = FakeAutosave(blocks)
    tasks = TaskRepository(db)
    session = RoomSessionBridge(
        (rooms, tasks, blocks, UndoRepository(db)),
        autosave,
        flag_guard,
        submit=lambda job: job(),
        parent=owner,
    )
    connect_room_flow(navigation, home, start, session)
    qml = create_engine(
        {
            "AppSettings": settings,
            "Navigation": navigation,
            "Pinning": pinning,
            "FlagGuard": flag_guard,
            "HomeModel": home,
            "StartRoom": start,
            "RoomSession": session,
            "Editors": EditorsBridge(parent=owner),
        }
    )
    warnings: list[str] = []
    qml.engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
    assert load_windows(qml.engine)
    main, panel = root_window(qml.engine, 0), root_window(qml.engine, 1)
    assert main is not None
    assert panel is not None
    wait(50)
    yield Running(
        qml,
        settings,
        navigation,
        main,
        panel,
        warnings,
        saved,
        pinner,
        flag_guard,
        kept,
        rooms,
        session,
        autosave,
        blocks,
        tasks,
    )
    # The engine goes first: bindings must never re-run against deleted bridges.
    for window in (main, panel):
        window.close()
    qml.engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    owner.deleteLater()
    db.close()


def test_two_windows_load_cleanly(running: Running) -> None:
    assert running.warnings == []
    assert running.main.title() == "Recon"
    assert running.panel.title() == "Recon Panel"  # the KWin rule matches this title


def test_main_window_starts_shown_and_panel_hidden(running: Running) -> None:
    assert running.main.isVisible()
    assert not running.panel.isVisible()


def test_main_window_size_fits_the_scaled_desktop(running: Running) -> None:
    assert (running.main.width(), running.main.height()) == (960, 640)
    assert running.main.width() <= 1280
    assert running.main.height() <= 720


def test_panel_width_limits(running: Running) -> None:
    assert running.panel.minimumWidth() == 360
    assert running.panel.maximumWidth() == 520


@pytest.mark.parametrize("running", [Settings(panel_width=480, kwin_pinning="off")], indirect=True)
def test_panel_opens_at_the_remembered_width(running: Running) -> None:
    running.navigation.showPanel()

    assert wait_until(running.panel.isVisible)
    assert running.panel.width() == 480


def test_resizing_the_panel_is_remembered(running: Running) -> None:
    running.navigation.showPanel()
    wait_until(running.panel.isVisible)

    running.panel.setWidth(470)

    # The resize reaches QML through the platform's event queue, a moment later.
    assert wait_until(lambda: running.settings.property("panelWidth") == 470)
    assert wait_until(lambda: running.saved == [Settings(panel_width=470, kwin_pinning="off")])


def test_panel_button_brings_back_a_closed_main_window(running: Running) -> None:
    running.navigation.showPanel()
    wait_until(running.panel.isVisible)
    running.main.close()
    assert wait_until(lambda: not running.main.isVisible())

    QMetaObject.invokeMethod(running.find(running.panel, "openHome"), "clicked")

    assert wait_until(running.main.isVisible)
    assert running.panel.isVisible()


def test_closing_the_main_window_leaves_the_panel_open(running: Running) -> None:
    running.navigation.showPanel()
    wait_until(running.panel.isVisible)

    running.main.close()
    wait(50)

    assert not running.main.isVisible()
    assert running.panel.isVisible()


def test_sidebar_switches_screens(running: Running) -> None:
    loader = running.find(running.main, "screenLoader")
    assert str(loader.property("source").toString()).endswith("screens/Home.qml")

    QMetaObject.invokeMethod(running.find(running.main, "nav-settings"), "clicked")
    wait(50)

    assert running.navigation.property("currentScreen") == "settings"
    assert str(loader.property("source").toString()).endswith("screens/Settings.qml")
    assert running.find(running.main, "nav-settings").property("selected") is True
    assert running.find(running.main, "nav-home").property("selected") is False


def test_both_windows_share_one_navigation_state(running: Running) -> None:
    running.navigation.open("settings")
    wait(20)

    assert running.find(running.main, "nav-settings").property("selected") is True
    assert running.warnings == []


# Task 1.4: the first-launch pin question ------------------------------------------------

ASKING = [Settings(kwin_pinning="ask")]


@pytest.mark.parametrize("running", ASKING, indirect=True)
def test_first_launch_asks_to_pin_the_panel(running: Running) -> None:
    question = running.find_object(running.main, "pinQuestion")

    assert wait_until(lambda: question.property("visible") is True)
    assert question.property("title") == (
        "Pin the Recon panel to the right edge of your screen while you work?"
    )
    assert question.property("primaryText") == "Pin the panel"
    assert running.warnings == []


@pytest.mark.parametrize("running", ASKING, indirect=True)
def test_pin_the_panel_pins_it(running: Running) -> None:
    question = running.find_object(running.main, "pinQuestion")
    wait_until(lambda: question.property("visible") is True)

    QMetaObject.invokeMethod(question, "accept")
    wait(50)

    assert running.settings.property("pinning") == "on"
    assert running.pinner.pinned[0].x == 860


@pytest.mark.parametrize("running", ASKING, indirect=True)
def test_not_now_never_asks_again(running: Running) -> None:
    question = running.find_object(running.main, "pinQuestion")
    wait_until(lambda: question.property("visible") is True)

    QMetaObject.invokeMethod(question, "reject")
    wait(50)

    assert running.settings.property("pinning") == "off"
    assert running.pinner.pinned == []


def test_no_question_once_answered(running: Running) -> None:
    wait(100)

    assert running.find_object(running.main, "pinQuestion").property("visible") is False


@pytest.mark.parametrize("running", [Settings(kwin_pinning="on")], indirect=True)
def test_pin_failure_shows_a_calm_toast(running: Running) -> None:
    running.pinner.method = None
    toast = running.find(running.main, "toast")

    QMetaObject.invokeMethod(
        running.qml.engine.rootContext().contextProperty("Pinning"), "applyIfOn"
    )

    assert wait_until(lambda: toast.property("shown") is True)
    assert toast.property("message").startswith("Couldn't pin the panel.")


# Task 1.6: the "Flag skipped" notice --------------------------------------------------------

MD5 = "5d41402abc4b2a76b9719d911017c592"


def test_braced_flag_notice_has_no_keep_button(running: Running) -> None:
    toast = running.find(running.panel, "panelToast")

    running.flag_guard.clean(7, "answer THM{x}", [])

    assert wait_until(lambda: toast.property("shown") is True)
    assert toast.property("message") == "Flag skipped. Recon never saves flags."
    assert toast.property("actionText") == ""


def test_hash_notice_offers_not_a_flag_keep_it(running: Running) -> None:
    toast = running.find(running.panel, "panelToast")
    restored: list[tuple[int, str]] = []
    running.flag_guard.keptRestored.connect(lambda block, text: restored.append((block, text)))

    running.flag_guard.clean(7, f"md5 {MD5}", [])
    assert wait_until(lambda: toast.property("shown") is True)
    assert toast.property("actionText") == "Not a flag, keep it"

    QMetaObject.invokeMethod(running.find(running.panel, "action"), "clicked")
    wait(20)

    assert running.kept == [(7, MD5)]
    assert restored == [(7, MD5)]
    assert toast.property("shown") is False


# Task 1.7: Home --------------------------------------------------------------------------

QUIET = Settings(kwin_pinning="off")
DNS = NewRoom(name="DNS in Detail", task_count=7)


def test_home_first_launch_shows_one_calm_start(running: Running) -> None:
    assert running.find(running.main, "emptyState").property("visible") is True
    assert running.find(running.main, "whereWasI").property("visible") is False
    assert running.find(running.main, "primaryAction").property("text") == "Start a room"
    assert running.find(running.main, "startNew").property("visible") is False
    assert running.warnings == []


@pytest.mark.parametrize("running", [WithRooms(QUIET, (DNS,))], indirect=True)
def test_home_with_a_room_in_progress(running: Running) -> None:
    assert running.find(running.main, "whereWasI").property("visible") is True
    assert running.find(running.main, "currentName").property("text") == "DNS in Detail"
    assert (
        running.find(running.main, "currentProgress").property("text") == "Task 1 of 7 · just now"
    )
    assert (
        running.find(running.main, "primaryAction").property("text")
        == "Carry on with DNS in Detail"
    )
    assert running.find(running.main, "startNew").property("visible") is True
    assert running.find(running.main, "emptyState").property("visible") is False
    assert running.warnings == []


# Task 1.8: Start a room ----------------------------------------------------------------


def _type(item: QObject, text: str) -> None:
    item.setProperty("text", text)


def _open_start(running: Running) -> None:
    QMetaObject.invokeMethod(running.find(running.main, "primaryAction"), "clicked")
    assert wait_until(lambda: running.navigation.property("currentScreen") == "start")
    wait(50)


def test_start_a_room_from_home(running: Running) -> None:
    _open_start(running)

    loader = running.find(running.main, "screenLoader")
    assert str(loader.property("source").toString()).endswith("screens/Start.qml")
    # Start sits under Home, so Home stays lit in the sidebar.
    assert running.find(running.main, "nav-home").property("selected") is True
    assert running.find(running.main, "roomName").property("activeFocus") is True
    assert running.find(running.main, "modeNew").property("checked") is True
    memory = running.find(running.main, "modeMemory")
    assert (memory.property("enabled"), memory.property("checked")) == (False, False)
    assert running.find(running.main, "moreFields").property("visible") is False
    assert running.warnings == []


def test_starting_opens_the_panel_and_home_shows_the_room(running: Running) -> None:
    _open_start(running)
    _type(running.find(running.main, "roomName"), "  DNS in Detail ")
    _type(running.find(running.main, "taskCount"), "7")

    QMetaObject.invokeMethod(running.find(running.main, "startButton"), "clicked")

    assert wait_until(running.panel.isVisible)
    assert running.navigation.property("currentScreen") == "home"
    room = running.rooms.current()
    assert room is not None
    assert (room.name, room.task_count, room.mode) == ("DNS in Detail", 7, "new")
    assert wait_until(
        lambda: running.find(running.main, "currentName").property("text") == "DNS in Detail"
    )
    assert running.warnings == []


def test_a_missing_name_is_asked_for_calmly(running: Running) -> None:
    _open_start(running)
    _type(running.find(running.main, "taskCount"), "7")
    running.find(running.main, "taskCount").forceActiveFocus()

    QMetaObject.invokeMethod(running.find(running.main, "startButton"), "clicked")
    wait(20)

    problem = running.find(running.main, "problem")
    assert problem.property("visible") is True
    assert problem.property("text") == "Give the room a name, then press Start."
    assert running.find(running.main, "roomName").property("activeFocus") is True
    assert running.rooms.recent() == []
    assert not running.panel.isVisible()


def test_a_bad_task_count_is_asked_for_calmly(running: Running) -> None:
    _open_start(running)
    _type(running.find(running.main, "roomName"), "DNS in Detail")

    QMetaObject.invokeMethod(running.find(running.main, "startButton"), "clicked")
    wait(20)

    assert running.find(running.main, "problem").property("text") == (
        "Number of tasks should be a whole number from 1 to 50."
    )
    assert running.find(running.main, "taskCount").property("activeFocus") is True


@pytest.mark.parametrize(
    "running",
    [WithRooms(QUIET, (NewRoom(name="Old", task_count=1, path="Pre Security", module="Linux"),))],
    indirect=True,
)
def test_path_and_module_are_remembered_behind_more(running: Running) -> None:
    QMetaObject.invokeMethod(running.find(running.main, "startNew"), "clicked")
    assert wait_until(lambda: running.navigation.property("currentScreen") == "start")
    wait(50)

    assert running.find(running.main, "placeSummary").property("text") == "Pre Security · Linux"
    QMetaObject.invokeMethod(running.find(running.main, "moreToggle"), "clicked")
    wait(20)
    assert running.find(running.main, "moreFields").property("visible") is True
    assert running.find(running.main, "pathField").property("text") == "Pre Security"
    _type(running.find(running.main, "moduleField"), "Networking")
    _type(running.find(running.main, "roomName"), "New one")
    _type(running.find(running.main, "taskCount"), "3")

    QMetaObject.invokeMethod(running.find(running.main, "startButton"), "clicked")

    assert wait_until(running.panel.isVisible)
    room = running.rooms.current()
    assert room is not None
    assert (room.path, room.module) == ("Pre Security", "Networking")


def test_back_returns_home_without_a_room(running: Running) -> None:
    _open_start(running)

    QMetaObject.invokeMethod(running.find(running.main, "backButton"), "clicked")

    assert wait_until(lambda: running.navigation.property("currentScreen") == "home")
    assert running.rooms.recent() == []


def test_start_works_from_the_keyboard(running: Running) -> None:
    _open_start(running)
    running.main.requestActivate()
    for char in "Linux":
        QTest.keyClick(running.main, char)
    QTest.keyClick(running.main, Qt.Key.Key_Tab)
    QTest.keyClick(running.main, "4")

    QTest.keyClick(running.main, Qt.Key.Key_Return)

    assert wait_until(running.panel.isVisible)
    room = running.rooms.current()
    assert room is not None
    assert (room.name, room.task_count) == ("Linux", 4)


def test_escape_goes_back_home(running: Running) -> None:
    _open_start(running)
    running.main.requestActivate()

    QTest.keyClick(running.main, Qt.Key.Key_Escape)

    assert wait_until(lambda: running.navigation.property("currentScreen") == "home")


# Task 1.9: the room session in the panel --------------------------------------------------


def _start_room(running: Running, name: str, tasks: int) -> None:
    start = running.qml.engine.rootContext().contextProperty("StartRoom")
    start.start(name, str(tasks), "", "")
    assert wait_until(running.panel.isVisible)
    wait(50)


def _editors(running: Running) -> list[QQuickItem]:
    found: list[QQuickItem] = []
    pending: list[QQuickItem] = [running.panel.contentItem()]
    while pending:
        item = pending.pop()
        if item.objectName() == "editor" and item.isVisible():
            found.append(item)
        pending.extend(item.childItems())
    return sorted(found, key=lambda e: e.mapToScene(e.position()).y())


def test_a_new_room_opens_on_task_one_ready_to_type(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)
    find = running.find

    assert find(running.panel, "noRoom").property("visible") is False
    assert find(running.panel, "roomName").property("text") == "DNS in Detail"
    assert find(running.panel, "taskLabel").property("text") == "Task 1 of 3"
    assert find(running.panel, "taskTitle").property("hint") == "Task 1"
    assert find(running.panel, "nextTask").property("text") == "Next task"
    editors = _editors(running)
    assert len(editors) == 1
    assert editors[0].property("hint").startswith("What's the one thing")
    assert wait_until(lambda: editors[0].property("activeFocus") is True)
    assert running.warnings == []


def test_add_bar_has_eight_buttons_with_two_coming_soon(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)
    types = [
        "key_idea",
        "command",
        "table",
        "screenshot",
        "question",
        "confused",
        "room_question",
        "voice",
    ]

    buttons = {t: running.find(running.panel, f"add-{t}") for t in types}

    assert {t for t, b in buttons.items() if not b.property("enabled")} == {"screenshot", "voice"}
    assert buttons["voice"].property("tip") == "Voice · Coming soon"
    assert buttons["command"].property("shortcutHint") == "Ctrl+2"


def test_typing_saves_and_flags_vanish(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)
    editor = _editors(running)[0]

    editor.setProperty("text", "TXT records hold text THM{n0pe}")
    wait(20)

    assert editor.property("text") == "TXT records hold text "
    (content,) = running.autosave.pending.values()
    assert content.text == "TXT records hold text "
    toast = running.find(running.panel, "panelToast")
    assert wait_until(lambda: toast.property("shown") is True)


def test_adding_a_block_from_the_bar_and_by_shortcut(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)

    QMetaObject.invokeMethod(running.find(running.panel, "add-command"), "clicked")
    wait(20)
    running.panel.requestActivate()
    QTest.keyClick(running.panel, Qt.Key.Key_5, Qt.KeyboardModifier.ControlModifier)
    wait(20)

    editors = _editors(running)
    assert [e.property("mono") for e in editors] == [False, True, False]
    assert editors[2].property("hint") == "Something you want answered later."
    assert wait_until(lambda: editors[2].property("activeFocus") is True)


def test_next_task_moves_on_and_finish_room_on_the_last(running: Running) -> None:
    _start_room(running, "DNS in Detail", 2)
    _editors(running)[0].setProperty("text", "Records map names to data")
    title = running.find(running.panel, "taskTitle")
    finished: list[int] = []
    running.session.finishRequested.connect(finished.append)

    QMetaObject.invokeMethod(running.find(running.panel, "nextTask"), "clicked")
    wait(20)

    assert running.find(running.panel, "taskLabel").property("text") == "Task 2 of 2"
    assert running.find(running.panel, "nextTask").property("text") == "Finish room"
    assert title.property("hint") == "Task 2"
    assert _editors(running)[0].property("text") == ""
    assert running.find(running.panel, "progressRing").property("value") == 0.5

    QMetaObject.invokeMethod(running.find(running.panel, "nextTask"), "clicked")
    wait(20)

    assert len(finished) == 1
    assert running.warnings == []


def test_next_plays_the_tick(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)
    tick = running.find(running.panel, "tick")

    QMetaObject.invokeMethod(running.find(running.panel, "nextTask"), "clicked")

    assert wait_until(lambda: tick.property("opacity") > 0)
    assert wait_until(lambda: tick.property("opacity") == 0, timeout_ms=3000)


def test_skip_this_task(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)

    QMetaObject.invokeMethod(running.find(running.panel, "skipTask"), "clicked")
    wait(20)

    assert running.find(running.panel, "taskLabel").property("text") == "Task 2 of 3"


def test_ctrl_return_is_next_task(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)
    running.panel.requestActivate()

    QTest.keyClick(running.panel, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    wait(20)

    assert running.find(running.panel, "taskLabel").property("text") == "Task 2 of 3"


def test_the_task_title_is_kept_per_task(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)
    title = running.find(running.panel, "taskTitle")
    title.forceActiveFocus()
    running.panel.requestActivate()
    for char in "Zones":
        QTest.keyClick(running.panel, char)

    QMetaObject.invokeMethod(running.find(running.panel, "nextTask"), "clicked")
    wait(20)

    assert title.property("text") == ""
    room = running.rooms.current()
    assert room is not None
    assert running.tasks.for_room(room.id)[0].title == "Zones"


@pytest.mark.parametrize("running", [WithRooms(QUIET, (DNS,))], indirect=True)
def test_carry_on_opens_the_room_in_the_panel(running: Running) -> None:
    QMetaObject.invokeMethod(running.find(running.main, "primaryAction"), "clicked")

    assert wait_until(running.panel.isVisible)
    assert running.find(running.panel, "roomName").property("text") == "DNS in Detail"
    assert running.find(running.panel, "taskLabel").property("text") == "Task 1 of 7"


def test_home_button_in_the_session_opens_home(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)
    running.main.close()

    QMetaObject.invokeMethod(running.find(running.panel, "sessionHome"), "clicked")

    assert wait_until(running.main.isVisible)


def test_a_failed_save_shows_a_calm_toast(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)

    running.session.failed.emit("Couldn't save to Recon's data folder.")

    toast = running.find(running.panel, "panelToast")
    assert wait_until(lambda: toast.property("shown") is True)
    assert toast.property("message") == "Couldn't save to Recon's data folder."


# Phase 1 acceptance: exactly one accent button per screen (ADHD rule 1) --------------------------


def _visible_primary_buttons(root: QQuickItem) -> list[str]:
    found: list[str] = []
    pending = [root]
    while pending:
        item = pending.pop()
        if not item.isVisible():
            continue
        if item.property("variant") == "primary":
            found.append(item.objectName() or str(item.property("text")))
        pending.extend(item.childItems())
    return found


@pytest.mark.parametrize(
    "running",
    [WithRooms(QUIET), WithRooms(QUIET, (DNS, NewRoom(name="Older", task_count=2)))],
    indirect=True,
)
@pytest.mark.parametrize(("screen", "accents"), [("home", 1), ("start", 1), ("settings", 0)])
def test_no_main_window_screen_has_more_than_one_accent_button(
    running: Running, screen: str, accents: int
) -> None:
    running.navigation.open(screen)
    wait(50)

    buttons = _visible_primary_buttons(running.main.contentItem())

    # Settings has no action of its own until task 1.14.
    assert len(buttons) == accents, buttons


def test_panel_has_at_most_one_accent_button(running: Running) -> None:
    running.navigation.showPanel()
    wait_until(running.panel.isVisible)

    assert len(_visible_primary_buttons(running.panel.contentItem())) <= 1


def test_panel_with_a_room_open_has_exactly_one_accent_button(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)

    assert _visible_primary_buttons(running.panel.contentItem()) == ["nextTask"]


def test_the_title_refills_when_another_room_opens(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)
    first = running.rooms.current()
    assert first is not None
    running.tasks.set_title(running.tasks.for_room(first.id)[0].id, "Zones")
    _start_room(running, "Linux Basics", 3)
    title = running.find(running.panel, "taskTitle")
    assert title.property("text") == ""

    running.session.open(first.id)
    wait(20)

    assert title.property("text") == "Zones"


def test_previous_task_from_the_footer_and_the_keyboard(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)
    back = running.find(running.panel, "previousTask")
    label = running.find(running.panel, "taskLabel")
    assert back.property("enabled") is False
    assert back.property("tip") == "Previous task"
    QMetaObject.invokeMethod(running.find(running.panel, "nextTask"), "clicked")
    QMetaObject.invokeMethod(running.find(running.panel, "nextTask"), "clicked")
    wait(20)
    assert label.property("text") == "Task 3 of 3"

    QMetaObject.invokeMethod(back, "clicked")
    wait(20)
    assert label.property("text") == "Task 2 of 3"

    # From inside a block's editor, too.
    editor = _editors(running)[0]
    assert wait_until(lambda: editor.property("activeFocus") is True)
    running.panel.requestActivate()
    QTest.keyClick(running.panel, Qt.Key.Key_Left, Qt.KeyboardModifier.AltModifier)
    wait(20)

    assert label.property("text") == "Task 1 of 3"
    assert back.property("enabled") is False
    assert running.find(running.panel, "nextTask").property("text") == "Next task"


# Task 1.10: block editors -------------------------------------------------------------------


def _blocks(running: Running) -> list[QQuickItem]:
    found: list[QQuickItem] = []
    pending: list[QQuickItem] = [running.panel.contentItem()]
    while pending:
        item = pending.pop()
        if item.objectName().startswith("block-") and item.isVisible():
            found.append(item)
        pending.extend(item.childItems())
    return sorted(found, key=lambda b: b.mapToScene(b.position()).y())


def _in(item: QQuickItem, name: str) -> QQuickItem:
    pending = [item]
    while pending:
        current = pending.pop()
        if current.objectName() == name:
            return current
        pending.extend(current.childItems())
    raise AssertionError(name)


def _add(running: Running, block_type: str) -> QQuickItem:
    QMetaObject.invokeMethod(running.find(running.panel, f"add-{block_type}"), "clicked")
    wait(20)
    return _blocks(running)[-1]


def test_table_block_shows_a_grid_preview(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)
    block = _add(running, "table")
    preview = _in(block, "tablePreview")
    assert preview.property("visible") is False

    _in(block, "editor").setProperty("text", "Port, Service\n53, DNS\n80, HTTP")
    wait(20)

    assert preview.property("visible") is True
    assert preview.property("columns") == 2
    assert len(preview.property("rows")) == 3
    assert running.warnings == []


def test_command_block_is_monospace(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)
    block = _add(running, "command")

    editor = _in(block, "editor")

    assert editor.property("mono") is True
    assert editor.property("font").family() == "JetBrains Mono"
    assert _in(block, "tablePreview").property("visible") is False
    assert _in(block, "answerArea").property("visible") is False


def test_room_question_answer_is_hidden_on_return(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)
    block = _add(running, "room_question")
    answer = _in(block, "answerEditor")
    toggle = _in(block, "answerToggle")
    assert answer.property("visible") is True
    assert toggle.property("visible") is False

    _in(block, "editor").setProperty("text", "Which port does DNS use?")
    answer.setProperty("text", "53 THM{n0}")
    wait(20)
    assert answer.property("text") == "53 "
    assert toggle.property("text") == "Hide answer"

    QMetaObject.invokeMethod(running.find(running.panel, "nextTask"), "clicked")
    QMetaObject.invokeMethod(running.find(running.panel, "previousTask"), "clicked")
    wait(20)

    block = _blocks(running)[1]
    assert _in(block, "answerEditor").property("visible") is False
    toggle = _in(block, "answerToggle")
    assert toggle.property("text") == "Show answer"
    QMetaObject.invokeMethod(toggle, "clicked")
    wait(20)
    assert _in(block, "answerEditor").property("visible") is True
    assert _in(block, "answerEditor").property("text") == "53 "


def _ids(running: Running) -> list[int]:
    return [int(b.property("blockId")) for b in _blocks(running)]


def test_alt_up_and_down_move_the_block_with_the_cursor(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)
    _add(running, "command")
    question = _add(running, "question")
    key, command, q = _ids(running)
    assert wait_until(lambda: _in(question, "editor").property("activeFocus") is True)
    running.panel.requestActivate()

    QTest.keyClick(running.panel, Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier)
    wait(20)
    assert _ids(running) == [key, q, command]
    QTest.keyClick(running.panel, Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier)
    wait(20)
    assert _ids(running) == [q, key, command]
    QTest.keyClick(running.panel, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
    wait(20)

    assert _ids(running) == [key, q, command]
    task = running.tasks.for_room(running.rooms.current().id)[0]  # type: ignore[union-attr]
    assert [b.id for b in running.blocks.for_task(task.id)] == [key, q, command]


def test_dragging_the_grip_moves_a_block(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)
    _add(running, "command")
    _add(running, "question")
    key, command, question = _ids(running)
    first, _second, third = _blocks(running)
    grip = _in(first, "grip")
    start = grip.mapToScene(QPointF(grip.width() / 2, grip.height() / 2)).toPoint()
    end = third.mapToScene(QPointF(third.width() / 2, third.height() - 2)).toPoint()

    QTest.mousePress(running.panel, Qt.MouseButton.LeftButton, pos=start)
    for step in range(1, 11):
        y = start.y() + (end.y() - start.y()) * step // 10
        QTest.mouseMove(running.panel, QPoint(start.x(), y))
        wait(10)
    assert running.find(running.panel, "dropLine").property("visible") is True
    QTest.mouseRelease(running.panel, Qt.MouseButton.LeftButton, pos=QPoint(start.x(), end.y()))
    wait(20)

    assert _ids(running) == [command, question, key]
    assert running.find(running.panel, "dropLine").property("visible") is False


# Task 1.11: undo ------------------------------------------------------------------------------


def _type_keys(running: Running, text: str) -> None:
    for char in text:
        QTest.keyClick(running.panel, char)


def test_ctrl_z_in_a_block_undoes_a_word_and_ctrl_shift_z_redoes(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)
    editor = _editors(running)[0]
    assert wait_until(lambda: editor.property("activeFocus") is True)
    running.panel.requestActivate()
    _type_keys(running, "MX is mail")

    QTest.keyClick(running.panel, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    wait(20)
    assert editor.property("text") == "MX is "
    assert editor.property("cursorPosition") == len("MX is ")

    QTest.keyClick(
        running.panel,
        Qt.Key.Key_Z,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    wait(20)
    assert editor.property("text") == "MX is mail"


def test_deleting_a_block_offers_undo_for_ten_seconds(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)
    first = _blocks(running)[0]
    assert _in(first, "deleteBlock").property("visible") is False  # never a blank page
    command = _add(running, "command")
    _in(command, "editor").setProperty("text", "dig MX")
    wait(20)
    delete = _in(command, "deleteBlock")
    assert delete.property("visible") is True
    assert delete.property("tip") == "Delete block"

    QMetaObject.invokeMethod(delete, "clicked")
    wait(20)

    assert len(_blocks(running)) == 1
    toast = running.find(running.panel, "panelToast")
    assert wait_until(lambda: toast.property("shown") is True)
    assert toast.property("message") == "Block deleted."
    assert toast.property("actionText") == "Undo"
    assert toast.property("timeout") == 10000

    QMetaObject.invokeMethod(running.find(running.panel, "action"), "clicked")
    wait(20)

    blocks = _blocks(running)
    assert len(blocks) == 2
    assert _in(blocks[1], "editor").property("text") == "dig MX"
    assert toast.property("shown") is False


def test_ctrl_shift_backspace_deletes_the_block_with_the_cursor(running: Running) -> None:
    _start_room(running, "DNS in Detail", 3)
    question = _add(running, "question")
    assert wait_until(lambda: _in(question, "editor").property("activeFocus") is True)
    running.panel.requestActivate()

    QTest.keyClick(
        running.panel,
        Qt.Key.Key_Backspace,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    wait(20)

    assert [b.property("blockType") for b in _blocks(running)] == ["key_idea"]
