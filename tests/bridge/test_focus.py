"""FocusBridge: time on task, focus blocks, the break nudge, and saving time."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from recon.bridge.focus import (
    AWAY_AFTER_S,
    BREAK_AFTER_S,
    MAX_TICK_S,
    SAVE_EVERY_S,
    FocusBridge,
)
from recon.db.connection import Database
from recon.db.migrate import migrate
from recon.db.models import NewRoom, Task
from recon.db.repositories import RoomRepository, TaskRepository
from recon.errors import StorageError
from tests.ui.qml_harness import SignalCounter, app


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@dataclass
class Setup:
    focus: FocusBridge
    clock: Clock
    rooms: RoomRepository
    tasks: TaskRepository
    chimes: list[int]
    chime_on: list[bool]
    room_id: int

    def task(self, index: int = 0) -> Task:
        return self.tasks.for_room(self.room_id)[index]

    def run(self, seconds: int, *, working: bool = True) -> None:
        """Let `seconds` pass, one tick a second; `working` keeps the user active."""
        for _ in range(seconds):
            self.clock.now += 1
            if working:
                self.focus.activity()
            self.focus.tick()


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    folder = tmp_path / "recon"
    folder.mkdir(mode=0o700)
    database = Database.open(folder / "app.db")
    migrate(database)
    yield database
    database.close()


def _setup(db: Database, tasks: TaskRepository | None = None) -> Setup:
    app()
    clock = Clock()
    rooms, tasks = RoomRepository(db), tasks or TaskRepository(db)
    room = rooms.create(NewRoom(name="DNS in Detail", task_count=3))
    chimes: list[int] = []
    chime_on = [False]
    focus = FocusBridge(
        tasks,
        lambda: chimes.append(1),
        lambda: chime_on[0],
        submit=lambda job: job(),
        monotonic=clock,
    )
    return Setup(focus, clock, rooms, tasks, chimes, chime_on, room.id)


@pytest.fixture
def setup(db: Database) -> Setup:
    return _setup(db)


def test_nothing_counts_without_a_task(setup: Setup) -> None:
    setup.run(10)

    assert setup.focus.property("seconds") == 0
    assert setup.focus.property("focusing") is False
    assert setup.focus.property("presets") == [15, 25, 45]


def test_time_on_task_counts_and_is_saved_to_task_and_room(setup: Setup) -> None:
    setup.focus.set_task(setup.task())

    setup.run(SAVE_EVERY_S + 5)

    assert setup.focus.property("seconds") == SAVE_EVERY_S + 5
    assert setup.focus.property("running") is True
    assert setup.task().time_spent_s == SAVE_EVERY_S
    room = setup.rooms.get(setup.room_id)
    assert room is not None
    assert room.time_spent_s == SAVE_EVERY_S


def test_switching_tasks_saves_the_rest_and_shows_the_new_tasks_time(setup: Setup) -> None:
    first = setup.task(0)
    setup.focus.set_task(first)
    setup.run(12)

    setup.focus.set_task(setup.task(1))

    assert setup.task(0).time_spent_s == 12
    assert setup.focus.property("seconds") == 0
    setup.run(3)
    # Back to the first task: its time carries on from where it was.
    setup.focus.set_task(first)  # read before the save landed: still shows 12
    assert setup.focus.property("seconds") == 12


def test_reading_in_the_browser_still_counts_but_away_stops(setup: Setup) -> None:
    setup.focus.set_task(setup.task())

    setup.run(AWAY_AFTER_S, working=False)
    assert setup.focus.property("seconds") == AWAY_AFTER_S
    setup.run(60, working=False)

    assert setup.focus.property("seconds") == AWAY_AFTER_S
    assert setup.focus.property("running") is False


def test_a_suspend_counts_as_a_short_tick_not_the_whole_gap(setup: Setup) -> None:
    setup.focus.set_task(setup.task())
    setup.focus.activity()

    setup.clock.now += 3600
    setup.focus.activity()
    setup.focus.tick()

    assert setup.focus.property("seconds") == int(MAX_TICK_S)


def test_break_nudge_once_after_ninety_minutes(setup: Setup) -> None:
    setup.focus.set_task(setup.task())
    nudges = SignalCounter(setup.focus, "breakSuggested()")

    setup.run(BREAK_AFTER_S - 1)
    assert nudges.count == 0
    setup.run(1)
    assert nudges.count == 1
    setup.run(600)
    assert nudges.count == 1


def test_a_long_pause_is_the_break(setup: Setup) -> None:
    setup.focus.set_task(setup.task())
    nudges = SignalCounter(setup.focus, "breakSuggested()")
    setup.run(BREAK_AFTER_S)
    setup.run(AWAY_AFTER_S + 2, working=False)

    setup.run(BREAK_AFTER_S - 1)
    assert nudges.count == 1
    setup.run(1)
    assert nudges.count == 2


@pytest.mark.parametrize("minutes", [15, 25, 45])
def test_focus_block_ends_gently(setup: Setup, minutes: int) -> None:
    done: list[int] = []
    setup.focus.focusDone.connect(done.append)
    setup.focus.set_task(setup.task())

    setup.focus.startFocus(minutes)
    setup.run(minutes * 30)
    assert setup.focus.property("focusing") is True
    assert setup.focus.property("focusMinutes") == minutes
    assert setup.focus.property("focusProgress") == pytest.approx(0.5)
    setup.run(minutes * 30)

    assert done == [minutes]
    assert setup.focus.property("focusing") is False
    assert setup.focus.property("focusProgress") == 0.0
    assert setup.chimes == []  # the chime is off by default


def test_the_chime_plays_only_when_settings_say_so(setup: Setup) -> None:
    setup.chime_on[0] = True
    setup.focus.startFocus(15)

    setup.run(15 * 60, working=False)

    assert setup.chimes == [1]


def test_stop_focus_and_odd_lengths(setup: Setup) -> None:
    done = SignalCounter(setup.focus, "focusDone(int)")
    setup.focus.startFocus(7)
    assert setup.focus.property("focusing") is False

    setup.focus.startFocus(25)
    setup.focus.stopFocus()
    setup.run(25 * 60)

    assert done.count == 0


def test_close_saves_what_is_left(setup: Setup) -> None:
    setup.focus.set_task(setup.task())
    setup.run(7)

    setup.focus.close()

    assert setup.task().time_spent_s == 7


def test_closing_the_room_stops_counting(setup: Setup) -> None:
    setup.focus.set_task(setup.task())
    setup.run(5)

    setup.focus.set_task(None)
    setup.run(5)

    assert setup.focus.property("seconds") == 0
    assert setup.task().time_spent_s == 5


class BrokenTasks(TaskRepository):
    def add_time(self, _task_id: int, _seconds: int) -> bool:
        raise StorageError


def test_failed_saves_are_logged_not_raised(db: Database) -> None:
    setup = _setup(db, BrokenTasks(db))
    setup.focus.set_task(setup.task())
    setup.run(SAVE_EVERY_S)

    setup.focus.close()

    assert setup.focus.property("seconds") == SAVE_EVERY_S


def test_add_time_ignores_nothing_and_unknown_tasks(setup: Setup) -> None:
    assert setup.tasks.add_time(setup.task().id, 0) is False
    assert setup.tasks.add_time(9999, 5) is False


def test_preview_plays_the_chime_even_when_it_is_off(setup: Setup) -> None:
    setup.focus.previewChime()

    assert setup.chimes == [1]
