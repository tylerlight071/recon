"""ProcessingBridge: one room at a time, plain progress, notifications, retry and resume."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject

from recon.bridge.processing import WAITING_TEXT, ProcessingBridge
from recon.db.models import Room
from recon.engine.stage import Manifest, StagedFile
from recon.errors import OllamaUnavailable
from recon.pipeline import Outcome, Step
from recon.services.notifications import Notice
from tests.ui.qml_harness import SignalCounter, app

MANIFEST = Manifest(
    run_id="20261028T120000-ab",
    room_id=1,
    files=tuple(
        StagedFile(path=f"n{i}.md", kind="concept", action="create", base_sha256=None, sha256="x")
        for i in range(3)
    ),
)


class FakeRunner:
    """A scripted pipeline: reports its steps, then ends as told."""

    def __init__(self) -> None:
        self.rooms: list[int] = []
        self.script: list[Step] = []
        self.outcome = Outcome(room="", cancelled=True)
        self.during: Callable[[], None] = lambda: None
        self.cancel_checks: list[bool] = []

    def run(
        self, room_id: int, report: Callable[[Step], None], cancelled: Callable[[], bool]
    ) -> Outcome:
        self.rooms.append(room_id)
        for step in self.script:
            report(step)
        self.during()
        self.cancel_checks.append(cancelled())
        return self.outcome


class Held:
    """A submit that holds jobs until the test runs them (a busy worker)."""

    def __init__(self) -> None:
        self.jobs: list[Callable[[], None]] = []

    def __call__(self, job: Callable[[], None]) -> None:
        self.jobs.append(job)

    def run_one(self) -> None:
        self.jobs.pop(0)()


def _room(room_id: int) -> Room:
    now = datetime(2026, 10, 28, tzinfo=UTC)
    return Room(
        id=room_id, platform="TryHackMe", path="", module="", name=f"Room {room_id}",
        task_count=1, mode="new", status="queued", created_at=now, updated_at=now,
        time_spent_s=0, last_task_index=1,
    )  # fmt: skip


_OWNERS: list[QObject] = []


@pytest.fixture(autouse=True)
def _delete_on_the_main_thread() -> Iterator[None]:
    # Tests here make cycles (a fake runner whose callback holds the bridge). Left to
    # Python's cycle collector, a QObject could be destroyed on whichever thread happens
    # to allocate next, such as an autosave thread in a later test, which crashes Qt.
    yield
    while _OWNERS:
        _OWNERS.pop().deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _bridge(
    runner: FakeRunner,
    submit: Callable[[Callable[[], None]], None] = lambda job: job(),
    waiting: Callable[[], list[Room]] = list,
) -> tuple[ProcessingBridge, list[Notice]]:
    app()
    owner = QObject()
    _OWNERS.append(owner)
    notices: list[Notice] = []
    bridge = ProcessingBridge(runner, notices.append, waiting, submit=submit, parent=owner)
    return bridge, notices


def test_a_ready_room_is_announced_and_shown() -> None:
    runner = FakeRunner()
    runner.script = [Step("DNS in Detail", 1, "Reading your notes")]
    runner.outcome = Outcome(room="DNS in Detail", manifest=MANIFEST)
    bridge, notices = _bridge(runner)
    ready = SignalCounter(bridge, "readyForReview(int)")
    bridge.show(1)

    bridge.enqueue(1)

    assert runner.rooms == [1]
    assert ready.count == 1
    assert bridge.property("line") == "Ready to review: 3 notes."
    assert bridge.property("busy") is False
    assert bridge.property("queued") == 0
    assert notices == [
        Notice(
            1,
            "DNS in Detail is ready to review",
            "Your notes are ready. Check them over, then Apply.",
            (("default", "Review"),),
        )
    ]


def test_progress_is_a_plain_line_and_a_step_number() -> None:
    runner = FakeRunner()
    runner.script = [
        Step("DNS", 1, "Reading your notes"),
        Step("DNS", 2, "Structuring 4 tasks with qwen3.5:9b"),
    ]
    bridge, _notices = _bridge(runner)
    bridge.show(1)
    seen: list[tuple[str, int, bool]] = []
    runner.during = lambda: seen.append(
        (bridge.property("line"), bridge.property("stepNumber"), bridge.property("busy"))
    )

    bridge.enqueue(1)

    assert seen == [("Structuring 4 tasks with qwen3.5:9b", 2, True)]
    assert bridge.property("steps") == 3
    assert bridge.property("line") == ""  # cancelled: nothing to say


def test_one_room_at_a_time_the_next_waits() -> None:
    held = Held()
    runner = FakeRunner()
    runner.script = [Step("A", 1, "Reading your notes")]
    bridge, _notices = _bridge(runner, held)

    bridge.enqueue(1)
    bridge.enqueue(2)
    bridge.enqueue(2)  # already waiting

    assert len(held.jobs) == 2
    assert bridge.property("queued") == 2
    bridge.show(2)
    assert bridge.property("line") == "Starting…"
    seen: list[str] = []
    runner.during = lambda: seen.append(bridge.property("line"))
    held.run_one()  # room 1 runs: room 2 waits behind it
    assert seen == [WAITING_TEXT]
    held.run_one()
    assert runner.rooms == [1, 2]
    assert bridge.property("queued") == 0


def test_a_problem_shows_with_retry_and_a_notification() -> None:
    runner = FakeRunner()
    runner.outcome = Outcome(room="DNS", problem=OllamaUnavailable.user_message)
    bridge, notices = _bridge(runner)
    bridge.show(1)

    bridge.enqueue(1)

    assert bridge.property("failed") is True
    assert bridge.property("line") == OllamaUnavailable.user_message
    assert notices[0].summary == "DNS couldn't be processed"
    assert notices[0].actions == (("default", "Open Recon"),)

    runner.outcome = Outcome(room="DNS", manifest=MANIFEST)
    bridge.retry()

    assert bridge.property("failed") is False
    assert runner.rooms == [1, 1]
    bridge.retry()  # nothing to retry now
    assert runner.rooms == [1, 1]


def test_an_unexpected_error_is_a_calm_problem(caplog: pytest.LogCaptureFixture) -> None:
    class Broken(FakeRunner):
        def run(self, *_args: object, **_kwargs: object) -> Outcome:
            raise RuntimeError("boom")

    bridge, notices = _bridge(Broken())
    bridge.show(1)

    bridge.enqueue(1)

    assert bridge.property("failed") is True
    assert "boom" not in bridge.property("line")
    assert notices[0].summary == "A room couldn't be processed"
    assert "RuntimeError" in caplog.text


def test_withdrawn_rooms_stop_and_say_nothing() -> None:
    held = Held()
    runner = FakeRunner()
    runner.outcome = Outcome(room="A", problem="whatever")
    bridge, notices = _bridge(runner, held)
    bridge.enqueue(1)
    bridge.enqueue(2)

    bridge.withdraw(2)  # waiting: dropped from the queue
    assert bridge.property("queued") == 1
    runner.during = lambda: bridge.withdraw(1)  # running: stops between steps
    held.run_one()
    held.run_one()

    assert runner.rooms == [1]
    assert runner.cancel_checks == [True]
    assert notices == []
    bridge.show(1)
    assert bridge.property("failed") is False


def test_quitting_stops_between_steps_and_skips_the_rest() -> None:
    held = Held()
    runner = FakeRunner()
    bridge, _notices = _bridge(runner, held)
    bridge.enqueue(1)
    bridge.enqueue(2)
    runner.during = bridge.close

    held.run_one()
    held.run_one()

    assert runner.rooms == [1]
    assert runner.cancel_checks == [True]


def test_resume_queues_waiting_rooms_in_order() -> None:
    runner = FakeRunner()
    bridge, _notices = _bridge(runner, waiting=lambda: [_room(4), _room(2)])

    bridge.resume()

    assert runner.rooms == [4, 2]


def test_resume_survives_a_failed_read(caplog: pytest.LogCaptureFixture) -> None:
    def broken() -> list[Room]:
        raise OllamaUnavailable

    runner = FakeRunner()
    bridge, _notices = _bridge(runner, waiting=broken)

    bridge.resume()

    assert runner.rooms == []
    assert "waiting rooms not read" in caplog.text


def test_a_notification_click_asks_to_open_the_room() -> None:
    bridge, _notices = _bridge(FakeRunner())
    opened: list[int] = []
    bridge.reviewRequested.connect(opened.append)

    bridge.action(7, "default")

    assert opened == [7]


def test_a_ready_room_says_one_note_kindly() -> None:
    runner = FakeRunner()
    runner.outcome = Outcome(
        room="R", manifest=MANIFEST.model_copy(update={"files": MANIFEST.files[:1]})
    )
    bridge, _notices = _bridge(runner)
    bridge.show(1)

    bridge.enqueue(1)

    assert bridge.property("line") == "Ready to review: 1 note."
